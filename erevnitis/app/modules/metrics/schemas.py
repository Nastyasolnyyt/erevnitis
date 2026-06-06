from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class MetricWrite(BaseModel):
    """Запись одной метрики (от агента / Pushgateway / скрипта)"""
    node_id: int
    metric_name: str
    metric_value: float
    recorded_at: Optional[datetime] = None


class MetricBulkWrite(BaseModel):
    """Пакетная запись метрик (экономит HTTP запросы)"""
    metrics: List[MetricWrite]


class MetricResponse(BaseModel):
    id: int
    node_id: int
    metric_name: str
    metric_value: float
    recorded_at: datetime

    class Config:
        from_attributes = True


class MetricSummary(BaseModel):
    """Последние значения всех метрик узла — для карточки сервера"""
    node_id: int
    hostname: str
    cpu_usage: Optional[float] = None
    ram_utilization: Optional[float] = None
    disk_free: Optional[float] = None
    net_rx_mb: Optional[float] = None
    net_tx_mb: Optional[float] = None
    uptime_hours: Optional[float] = None
    last_updated: Optional[datetime] = None


class MetricPoint(BaseModel):
    """Одна точка временного ряда для графика"""
    ts: str   # ISO timestamp
    value: float


class MetricSeries(BaseModel):
    """Временной ряд для Chart.js"""
    node_id: int
    metric_name: str
    points: List[MetricPoint]
