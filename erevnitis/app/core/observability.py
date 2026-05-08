"""
observability.py — Наблюдаемость: логирование и метрики
Задание 2 ЛР3: журналы событий + сбор показателей производительности
"""
import time
import logging
import json
from datetime import datetime
from collections import defaultdict, deque
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# ── Настройка структурированного логгера ──────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("erevnitis")

# ── Хранилище метрик (in-memory, для демонстрации) ────────────────────────────
class MetricsStore:
    """Простое хранилище метрик производительности"""

    def __init__(self):
        self.request_count = 0
        self.error_count = 0
        self.response_times: deque = deque(maxlen=1000)   # последние 1000 запросов
        self.endpoint_stats: dict = defaultdict(lambda: {"count": 0, "total_ms": 0.0})
        self.status_codes: dict = defaultdict(int)
        self.start_time = datetime.utcnow()

    def record_request(self, method: str, path: str, status: int, duration_ms: float):
        self.request_count += 1
        self.response_times.append(duration_ms)
        self.status_codes[str(status)] += 1
        key = f"{method} {path}"
        self.endpoint_stats[key]["count"] += 1
        self.endpoint_stats[key]["total_ms"] += duration_ms
        if status >= 400:
            self.error_count += 1

    def get_summary(self) -> dict:
        times = list(self.response_times)
        avg_ms = sum(times) / len(times) if times else 0
        max_ms = max(times) if times else 0
        p95 = sorted(times)[int(len(times) * 0.95)] if len(times) > 20 else max_ms

        top_endpoints = sorted(
            [{"endpoint": k, **v,
              "avg_ms": round(v["total_ms"] / v["count"], 2)}
             for k, v in self.endpoint_stats.items()],
            key=lambda x: x["count"], reverse=True
        )[:5]

        return {
            "uptime_seconds": int((datetime.utcnow() - self.start_time).total_seconds()),
            "total_requests": self.request_count,
            "error_count": self.error_count,
            "error_rate_pct": round(self.error_count / max(self.request_count, 1) * 100, 2),
            "avg_response_ms": round(avg_ms, 2),
            "max_response_ms": round(max_ms, 2),
            "p95_response_ms": round(p95, 2),
            "status_codes": dict(self.status_codes),
            "top_endpoints": top_endpoints,
        }


metrics = MetricsStore()


# ── Middleware: логирование каждого запроса ────────────────────────────────────
class LoggingMetricsMiddleware(BaseHTTPMiddleware):
    """
    Перехватывает каждый HTTP запрос:
    - логирует метод, путь, статус, время ответа
    - обновляет MetricsStore
    """
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()

        # Лог входящего запроса
        logger.info(
            "REQUEST  %s %s  client=%s",
            request.method, request.url.path,
            request.client.host if request.client else "unknown"
        )

        try:
            response: Response = await call_next(request)
            duration_ms = (time.perf_counter() - start) * 1000

            # Лог ответа
            level = logging.WARNING if response.status_code >= 400 else logging.INFO
            logger.log(level,
                "RESPONSE %s %s → %d  (%.1f ms)",
                request.method, request.url.path,
                response.status_code, duration_ms
            )

            # Запись метрики
            metrics.record_request(
                request.method,
                request.url.path,
                response.status_code,
                duration_ms
            )

            # Добавляем заголовок с временем ответа
            response.headers["X-Response-Time-Ms"] = f"{duration_ms:.1f}"
            return response

        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "ERROR    %s %s → EXCEPTION: %s  (%.1f ms)",
                request.method, request.url.path, str(exc), duration_ms
            )
            metrics.record_request(request.method, request.url.path, 500, duration_ms)
            raise
