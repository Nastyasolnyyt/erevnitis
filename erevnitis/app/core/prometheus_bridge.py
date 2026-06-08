import asyncio
import httpx
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.modules.nodes.models import Node
from app.modules.metrics.models import MetricHistory

logger = logging.getLogger("erevnitis.prometheus_bridge")

# URL Прометея внутри сети docker-compose
PROMETHEUS_URL = "http://prometheus:9090/api/v1/query"

# Словарь PromQL запросов. 
# Используем селектор {hostname="{hostname}"}, чтобы динамически опрашивать нужный сервер.
PROM_QUERIES = {
    "cpu_usage": '100 - (avg by (hostname) (rate(node_cpu_seconds_total{mode="idle", hostname="{hostname}"}[1m])) * 100)',
    "ram_utilization": '100 - (node_memory_MemAvailable_bytes{hostname="{hostname}"} / node_memory_MemTotal_bytes{hostname="{hostname}"} * 100)',
    "disk_free": '(node_filesystem_free_bytes{mountpoint="/", hostname="{hostname}"} / node_filesystem_size_bytes{mountpoint="/", hostname="{hostname}"}) * 100',
    "net_rx_mb": 'rate(node_network_receive_bytes_total{device=~"eth0|enp.*|wlan.*", hostname="{hostname}"}[1m]) / 1024 / 1024',
    "net_tx_mb": 'rate(node_network_transmit_bytes_total{device=~"eth0|enp.*|wlan.*", hostname="{hostname}"}[1m]) / 1024 / 1024',
    "uptime_hours": 'node_time_seconds{hostname="{hostname}"} - node_boot_time_seconds{hostname="{hostname}"} / 3600'
}

async def fetch_metric_from_prom(client: httpx.AsyncClient, hostname: str, query_template: str) -> float:
    """Делает запрос к Prometheus API и вытаскивает float значение"""
    query = query_template.format(hostname=hostname)
    try:
        response = await client.get(PROMETHEUS_URL, params={"query": query}, timeout=5.0)
        if response.status_code == 200:
            data = response.json()
            results = data.get("data", {}).get("result", [])
            if results:
                # Забираем значение из структуры Прометея: [timestamp, "value"]
                return float(results[0]["value"][1])
    except Exception as e:
        logger.error(f"Ошибка запроса к Prometheus для {hostname}: {e}")
    return None

async def prometheus_sync_loop(interval_seconds: int = 15):
    """Бесконечный цикл сбора метрик из Прометея в БД Erevnitis"""
    logger.info("Запущен фоновый мост интеграции Prometheus -> Erevnitis")
    
    async with httpx.AsyncClient() as client:
        while True:
            db: Session = SessionLocal()
            try:
                # Вытаскиваем из базы все Linux-серверы
                nodes = db.query(Node).filter(Node.os_type == "linux", Node.status == True).all()
                
                for node in nodes:
                    now = datetime.utcnow()
                    metrics_to_save = []

                    for metric_name, query_template in PROM_QUERIES.items():
                        val = await fetch_metric_from_prom(client, node.hostname, query_template)
                        
                        if val is not None:
                            metrics_to_save.append(
                                MetricHistory(
                                    node_id=node.id,
                                    metric_name=metric_name,
                                    metric_value=round(val, 2),
                                    recorded_at=now
                                )
                            )
                    
                    if metrics_to_save:
                        db.bulk_save_objects(metrics_to_save)
                        node.last_seen = now
                        node.status = True
                        db.commit()
                        logger.info(f"Синхронизировано {len(metrics_to_save)} метрик для хоста {node.hostname}")
                        
            except Exception as e:
                logger.error(f"Ошибка в цикле синхронизации: {e}")
                db.rollback()
            finally:
                db.close()
                
            await asyncio.sleep(interval_seconds)