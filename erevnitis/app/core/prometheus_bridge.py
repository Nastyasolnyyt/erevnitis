"""
prometheus_bridge.py — мост Prometheus -> Erevnitis metrics_history

"""
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

# PromQL запросы с {job} лейблом
# В prometheus.yml у тебя: job_name: 'ubuntu-185'
# это значение попадает в лейбл job= у всех метрик
PROM_QUERIES = {
    "cpu_usage": (
        '100 - (avg by(job)(rate(node_cpu_seconds_total{{mode="idle",job="{job}"}}[1m])) * 100)'
    ),
    "ram_utilization": (
        '100 - (node_memory_MemAvailable_bytes{{job="{job}"}} '
        '/ node_memory_MemTotal_bytes{{job="{job}"}} * 100)'
    ),
    "disk_free": (
        '(node_filesystem_free_bytes{{mountpoint="/",job="{job}",fstype!="tmpfs"}} '
        '/ node_filesystem_size_bytes{{mountpoint="/",job="{job}",fstype!="tmpfs"}}) * 100'
    ),
    "net_rx_mb": (
        'rate(node_network_receive_bytes_total{{job="{job}",device=~"eth0|ens.*|enp.*|wlan0"}}[1m])'
        ' / 1048576'
    ),
    "net_tx_mb": (
        'rate(node_network_transmit_bytes_total{{job="{job}",device=~"eth0|ens.*|enp.*|wlan0"}}[1m])'
        ' / 1048576'
    ),
    "uptime_hours": (
        '(node_time_seconds{{job="{job}"}} - node_boot_time_seconds{{job="{job}"}}) / 3600'
    ),
}


async def fetch_metric(
    client: httpx.AsyncClient,
    job: str,
    metric_name: str,
    query_template: str
) -> float | None:
    """Запрашивает одну метрику из Prometheus API."""
    query = query_template.format(job=job)
    try:
        resp = await client.get(
            PROMETHEUS_URL,
            params={"query": query},
            timeout=5.0
        )
        if resp.status_code != 200:
            logger.warning(f"Prometheus вернул {resp.status_code} для {metric_name}@{job}")
            return None

        data = resp.json()
        results = data.get("data", {}).get("result", [])
        if not results:
            logger.debug(f"Нет данных в Prometheus: {metric_name}@{job}")
            return None

        value = float(results[0]["value"][1])
        # Защита от NaN/Inf которые иногда возвращает Prometheus
        if value != value or value == float("inf"):
            return None
        return value

    except Exception as e:
        logger.error(f"Ошибка запроса {metric_name}@{job}: {e}")
        return None


def get_prometheus_job(node: Node) -> str:
    """
    Определяет какой job= лейбл использовать для этого узла.

    Логика:
    - Поле 'purpose' в Node используем как имя job в Prometheus
      (в prometheus.yml: job_name: 'ubuntu-185', поле purpose = 'ubuntu-185')
    - Если purpose пустой — пробуем hostname
    """
    if node.purpose and node.purpose.strip():
        return node.purpose.strip()
    return node.hostname


async def prometheus_sync_loop(interval_seconds: int = 15):
    """
    Бесконечный фоновый цикл: каждые interval_seconds секунд
    опрашивает Prometheus и сохраняет метрики в metrics_history.
    """
    logger.info(
        f"Запущен мост Prometheus -> Erevnitis "
        f"(интервал {interval_seconds}с, URL={PROMETHEUS_URL})"
    )

    # Небольшая задержка при старте — даём Prometheus время подняться
    await asyncio.sleep(10)

    async with httpx.AsyncClient() as client:
        while True:
            db: Session = SessionLocal()
            synced_nodes = 0
            synced_points = 0

            try:
                # Берём все активные узлы Linux
                nodes = (
                    db.query(Node)
                    .filter(Node.os_type == "linux")
                    .all()
                )

                if not nodes:
                    logger.debug("Нет Linux-узлов в БД, пропускаем синхронизацию")
                else:
                    now = datetime.utcnow()

                    for node in nodes:
                        job = get_prometheus_job(node)
                        metrics_batch = []

                        for metric_name, query_template in PROM_QUERIES.items():
                            val = await fetch_metric(client, job, metric_name, query_template)
                            if val is not None:
                                metrics_batch.append(
                                    MetricHistory(
                                        node_id=node.id,
                                        metric_name=metric_name,
                                        metric_value=round(val, 2),
                                        recorded_at=now,
                                    )
                                )

                        if metrics_batch:
                            db.bulk_save_objects(metrics_batch)
                            node.last_seen = now
                            node.status = True
                            synced_nodes += 1
                            synced_points += len(metrics_batch)
                        else:
                            logger.warning(
                                f"Нет данных из Prometheus для узла '{node.hostname}' "
                                f"(job='{job}'). "
                                f"Проверь: 1) node_exporter запущен на {node.ip_address}:9100 "
                                f"2) В prometheus.yml job_name совпадает с полем 'purpose' узла"
                            )

                    if synced_points > 0:
                        db.commit()
                        logger.info(
                            f"Синхронизировано: {synced_points} точек "
                            f"для {synced_nodes} узлов"
                        )

            except Exception as e:
                logger.error(f"Критическая ошибка в цикле синхронизации: {e}", exc_info=True)
                db.rollback()
            finally:
                db.close()

            await asyncio.sleep(interval_seconds)