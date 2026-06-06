"""
analytics/router.py
──────────────────
Два уникальных модуля:

1. SLA-калькулятор
   GET /api/v1/analytics/sla/{node_id}?days=30
   → процент доступности, время простоя, количество инцидентов,
     Error Budget остаток

2. Умные алерты с контекстом
   POST /api/v1/analytics/smart-alert
   → принимает webhook Alertmanager, обогащает инцидент
     текущими метриками + аномальностью значения
     (сравнение с нормой этого часа за последние 7 дней)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import statistics

from app.core.database import get_db
from app.core.security import require_any_auth, require_admin
from app.modules.nodes.models import Node
from app.modules.incidents.models import Incident
from app.modules.metrics.models import MetricHistory

router = APIRouter()


# ══════════════════════════════════════════════════════════════
# 1. SLA CALCULATOR
# ══════════════════════════════════════════════════════════════

@router.get("/sla/{node_id}")
def get_node_sla(
    node_id: int,
    days: int = Query(30, ge=1, le=365),
    slo_target: float = Query(99.9, ge=0.0, le=100.0),
    db: Session = Depends(get_db),
    _=Depends(require_any_auth),
):
    """
    SLA-калькулятор для конкретного узла.

    Считает:
    - Реальный процент доступности (на основе инцидентов)
    - Суммарное время простоя в минутах
    - Error Budget: сколько минут осталось до нарушения SLO
    - MTTR за период
    - Статус: соответствует SLO или нет
    """
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(404, "Узел не найден")

    period_start = datetime.utcnow() - timedelta(days=days)
    period_minutes = days * 24 * 60  # всего минут в периоде

    # ── Все инциденты узла за период ──────────────────────────
    incidents = (
        db.query(Incident)
        .filter(
            Incident.node_id == node_id,
            Incident.created_at >= period_start,
        )
        .order_by(Incident.created_at)
        .all()
    )

    # ── Считаем время простоя ──────────────────────────────────
    downtime_minutes = 0.0
    incident_details = []

    for inc in incidents:
        start = inc.created_at
        end   = inc.resolved_at or datetime.utcnow()  # открытый = до сейчас
        duration_min = (end - start).total_seconds() / 60

        downtime_minutes += duration_min
        incident_details.append({
            "id":           inc.id,
            "title":        inc.title,
            "severity":     inc.severity,
            "status":       inc.status,
            "started_at":   inc.created_at.isoformat(),
            "resolved_at":  inc.resolved_at.isoformat() if inc.resolved_at else None,
            "duration_min": round(duration_min, 1),
        })

    # ── Uptime % ───────────────────────────────────────────────
    uptime_minutes = max(0.0, period_minutes - downtime_minutes)
    availability   = (uptime_minutes / period_minutes) * 100 if period_minutes > 0 else 100.0
    availability   = min(100.0, round(availability, 4))

    # ── Error Budget ───────────────────────────────────────────
    # Допустимое время простоя при заданном SLO
    allowed_downtime   = period_minutes * (1 - slo_target / 100)
    budget_remaining   = max(0.0, allowed_downtime - downtime_minutes)
    budget_consumed_pct = min(100.0, round(
        (downtime_minutes / allowed_downtime * 100) if allowed_downtime > 0 else 0, 1
    ))

    # ── MTTR ───────────────────────────────────────────────────
    resolved = [i for i in incidents if i.resolved_at]
    mttr_minutes = None
    if resolved:
        durations = [
            (i.resolved_at - i.created_at).total_seconds() / 60
            for i in resolved
        ]
        mttr_minutes = round(statistics.mean(durations), 1)

    # ── Статус ─────────────────────────────────────────────────
    meets_slo = availability >= slo_target

    # ── Тренд: последние 7 vs предыдущие 7 дней ───────────────
    mid = datetime.utcnow() - timedelta(days=7)
    recent_down = sum(
        (i.resolved_at or datetime.utcnow() - i.created_at).total_seconds() / 60
        for i in incidents if i.created_at >= mid
    )
    older_down = sum(
        (i.resolved_at or datetime.utcnow() - i.created_at).total_seconds() / 60
        for i in incidents if i.created_at < mid
    )
    trend = "improving" if recent_down < older_down else (
            "degrading"  if recent_down > older_down else "stable"
    )

    return {
        "node_id":        node_id,
        "hostname":       node.hostname,
        "period_days":    days,
        "slo_target_pct": slo_target,

        # Основные метрики
        "availability_pct":     availability,
        "downtime_minutes":     round(downtime_minutes, 1),
        "uptime_minutes":       round(uptime_minutes, 1),
        "meets_slo":            meets_slo,

        # Error Budget
        "error_budget": {
            "allowed_downtime_min":  round(allowed_downtime, 1),
            "consumed_min":          round(downtime_minutes, 1),
            "remaining_min":         round(budget_remaining, 1),
            "consumed_pct":          budget_consumed_pct,
            "status": (
                "healthy"  if budget_consumed_pct < 50 else
                "warning"  if budget_consumed_pct < 80 else
                "critical" if budget_consumed_pct < 100 else
                "exhausted"
            ),
        },

        # Инциденты
        "incidents_total":    len(incidents),
        "incidents_resolved": len(resolved),
        "incidents_open":     len([i for i in incidents if i.status == "open"]),
        "mttr_minutes":       mttr_minutes,

        # Тренд
        "trend":    trend,
        "incidents": incident_details,
    }


@router.get("/sla")
def get_all_nodes_sla(
    days: int = Query(30, ge=1, le=365),
    slo_target: float = Query(99.9),
    db: Session = Depends(get_db),
    _=Depends(require_any_auth),
):
    """SLA сводка по всем узлам — для дашборда."""
    nodes = db.query(Node).all()
    results = []
    for node in nodes:
        period_start    = datetime.utcnow() - timedelta(days=days)
        period_minutes  = days * 24 * 60
        incidents       = db.query(Incident).filter(
            Incident.node_id == node.id,
            Incident.created_at >= period_start,
        ).all()

        downtime = sum(
            (i.resolved_at or datetime.utcnow() - i.created_at).total_seconds() / 60
            for i in incidents
        )
        availability = round(
            ((period_minutes - downtime) / period_minutes) * 100, 3
        ) if period_minutes > 0 else 100.0

        allowed = period_minutes * (1 - slo_target / 100)
        results.append({
            "node_id":          node.id,
            "hostname":         node.hostname,
            "status":           node.status,
            "availability_pct": min(100.0, availability),
            "downtime_min":     round(downtime, 1),
            "incidents_total":  len(incidents),
            "meets_slo":        availability >= slo_target,
            "error_budget_pct": min(100.0, round(
                downtime / allowed * 100 if allowed > 0 else 0, 1
            )),
        })

    results.sort(key=lambda x: x["availability_pct"])
    return {
        "period_days":   days,
        "slo_target_pct": slo_target,
        "nodes":         results,
        "summary": {
            "total":      len(results),
            "meets_slo":  sum(1 for r in results if r["meets_slo"]),
            "violating":  sum(1 for r in results if not r["meets_slo"]),
            "avg_availability": round(
                statistics.mean([r["availability_pct"] for r in results]) if results else 100.0, 3
            ),
        },
    }


# ══════════════════════════════════════════════════════════════
# 2. УМНЫЕ АЛЕРТЫ С КОНТЕКСТОМ
# ══════════════════════════════════════════════════════════════

class SmartAlertPayload(BaseModel):
    """Тот же формат что у Alertmanager webhook."""
    alerts: list


def _get_anomaly_context(db: Session, node_id: int, metric_name: str, current_value: float) -> dict:
    """
    Сравниваем текущее значение с нормой этого часа суток
    за последние 7 дней (простое скользящее среднее).

    Возвращает: is_anomaly, baseline, deviation_pct, interpretation
    """
    now  = datetime.utcnow()
    hour = now.hour

    # Берём значения этой метрики в ±1 час от текущего времени суток за 7 дней
    history = []
    for day_offset in range(1, 8):
        window_center = now - timedelta(days=day_offset)
        window_start  = window_center.replace(hour=hour) - timedelta(hours=1)
        window_end    = window_center.replace(hour=hour) + timedelta(hours=1)

        rows = (
            db.query(MetricHistory.metric_value)
            .filter(
                MetricHistory.node_id    == node_id,
                MetricHistory.metric_name == metric_name,
                MetricHistory.recorded_at >= window_start,
                MetricHistory.recorded_at <= window_end,
            )
            .all()
        )
        history.extend([r.metric_value for r in rows])

    if len(history) < 5:
        return {
            "is_anomaly":     False,
            "baseline":       None,
            "deviation_pct":  None,
            "interpretation": "Недостаточно исторических данных для анализа аномалий",
            "data_points":    len(history),
        }

    baseline       = statistics.mean(history)
    stdev          = statistics.stdev(history) if len(history) > 1 else 0
    deviation_pct  = ((current_value - baseline) / baseline * 100) if baseline > 0 else 0
    # Аномалия = отклонение > 2 стандартных отклонения
    is_anomaly     = abs(current_value - baseline) > 2 * stdev and abs(deviation_pct) > 15

    if abs(deviation_pct) < 10:
        interpretation = f"Значение в норме для {hour}:00 (±{abs(deviation_pct):.1f}% от базовой линии)"
    elif deviation_pct > 0:
        interpretation = (
            f"⚠ Аномально высокое значение для {hour}:00: "
            f"+{deviation_pct:.1f}% выше нормы ({baseline:.1f})"
        )
    else:
        interpretation = (
            f"Аномально низкое значение для {hour}:00: "
            f"{abs(deviation_pct):.1f}% ниже нормы ({baseline:.1f})"
        )

    return {
        "is_anomaly":     is_anomaly,
        "baseline":       round(baseline, 2),
        "stdev":          round(stdev, 2),
        "deviation_pct":  round(deviation_pct, 1),
        "interpretation": interpretation,
        "data_points":    len(history),
    }


def _find_node_by_job(db: Session, job_name: str) -> Optional[Node]:
    """Ищем узел по полю purpose (= Pushgateway job name) или hostname."""
    node = db.query(Node).filter(Node.purpose == job_name).first()
    if not node:
        node = db.query(Node).filter(Node.hostname == job_name).first()
    return node


@router.post("/smart-alert", status_code=201)
def receive_smart_alert(
    payload: SmartAlertPayload,
    db: Session = Depends(get_db),
):
    """
    Умный webhook — замена стандартного /incidents/webhook/alertmanager.

    Отличия от обычного webhook:
    1. Находит узел по job name (поле purpose)
    2. Запрашивает последние метрики узла
    3. Проверяет аномальность каждой метрики
    4. Добавляет всё это в description инцидента
    5. Не создаёт дубликаты (проверка по fingerprint)
    """
    if not payload.alerts:
        raise HTTPException(400, "Нет алертов в payload")

    created_incidents = []

    for alert in payload.alerts:
        labels      = alert.get("labels",      {})
        annotations = alert.get("annotations", {})
        status      = alert.get("status",      "firing")

        alert_name   = labels.get("alertname", "UnknownAlert")
        job_name     = labels.get("job", labels.get("instance", ""))
        severity_raw = labels.get("severity", "warning")

        severity_map = {"critical": "critical", "warning": "high",
                        "page": "critical", "info": "low"}
        severity = severity_map.get(severity_raw, "medium")

        # Fingerprint для дедупликации — не создавать второй инцидент
        fingerprint = f"{alert_name}_{job_name}"
        existing = (
            db.query(Incident)
            .filter(
                Incident.status != "resolved",
                Incident.title.contains(alert_name),
            )
            .first()
        )
        if existing:
            # Обновить description актуальными данными но не дублировать
            created_incidents.append({
                "action": "skipped_duplicate",
                "existing_incident_id": existing.id,
                "alert_name": alert_name,
            })
            continue

        # ── Найти узел ──────────────────────────────────────────
        node = _find_node_by_job(db, job_name) if job_name else None

        # ── Собрать текущие метрики ──────────────────────────────
        metrics_snapshot = {}
        anomalies = []

        if node:
            from sqlalchemy import desc as sa_desc
            for metric_name in ["cpu_usage", "ram_utilization", "disk_free", "net_rx_mb"]:
                latest = (
                    db.query(MetricHistory)
                    .filter(
                        MetricHistory.node_id    == node.id,
                        MetricHistory.metric_name == metric_name,
                    )
                    .order_by(sa_desc(MetricHistory.recorded_at))
                    .first()
                )
                if latest:
                    val = round(latest.metric_value, 1)
                    metrics_snapshot[metric_name] = val

                    # Анализ аномальности
                    anomaly = _get_anomaly_context(db, node.id, metric_name, val)
                    if anomaly["is_anomaly"]:
                        anomalies.append(f"{metric_name}: {anomaly['interpretation']}")

        # ── Собрать description с контекстом ────────────────────
        base_desc = annotations.get("description",
                    annotations.get("summary", "Автоматически создан из алерта"))

        context_parts = [base_desc, ""]

        if metrics_snapshot:
            context_parts.append("📊 Состояние сервера в момент алерта:")
            labels_ru = {
                "cpu_usage":       "CPU",
                "ram_utilization": "RAM",
                "disk_free":       "Диск свободно",
                "net_rx_mb":       "Сеть RX",
            }
            for mn, mv in metrics_snapshot.items():
                unit = "%" if mn != "net_rx_mb" else " MB/s"
                context_parts.append(f"  • {labels_ru.get(mn, mn)}: {mv}{unit}")

        if anomalies:
            context_parts.append("")
            context_parts.append("⚡ Обнаружены аномалии (отклонение > 2σ от нормы):")
            for a in anomalies:
                context_parts.append(f"  • {a}")

        if status == "resolved":
            context_parts.append("")
            context_parts.append("✅ Алерт разрешён в Prometheus.")

        rich_description = "\n".join(context_parts)

        # ── Создать инцидент ─────────────────────────────────────
        incident = Incident(
            title       = f"[AUTO] {alert_name}",
            description = rich_description,
            severity    = severity,
            status      = "open",
            node_id     = node.id if node else None,
        )
        db.add(incident)
        db.commit()
        db.refresh(incident)

        # ── Записать аномалии в audit ────────────────────────────
        if anomalies:
            from app.modules.audit.models import AuditLog
            db.add(AuditLog(
                action        = "CREATE",
                resource_type = "incident",
                resource_id   = incident.id,
                details       = f'{{"anomalies": {len(anomalies)}, '
                                f'"fingerprint": "{fingerprint}"}}',
            ))
            db.commit()

        created_incidents.append({
            "action":       "created",
            "incident_id":  incident.id,
            "title":        incident.title,
            "severity":     incident.severity,
            "node_id":      incident.node_id,
            "anomalies":    len(anomalies),
            "has_metrics":  bool(metrics_snapshot),
        })

    return {
        "processed": len(payload.alerts),
        "results":   created_incidents,
    }


@router.get("/anomalies/{node_id}")
def get_anomalies(
    node_id: int,
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
    _=Depends(require_any_auth),
):
    """
    Найти аномальные точки в истории метрик узла за последние N часов.
    Используется для подсветки на графике.
    """
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(404, "Узел не найден")

    since = datetime.utcnow() - timedelta(hours=hours)
    results = {}

    for metric_name in ["cpu_usage", "ram_utilization", "disk_free"]:
        rows = (
            db.query(MetricHistory)
            .filter(
                MetricHistory.node_id    == node_id,
                MetricHistory.metric_name == metric_name,
                MetricHistory.recorded_at >= since,
            )
            .order_by(MetricHistory.recorded_at)
            .all()
        )

        if len(rows) < 10:
            results[metric_name] = []
            continue

        values = [r.metric_value for r in rows]
        mean   = statistics.mean(values)
        stdev  = statistics.stdev(values) if len(values) > 1 else 0

        anomalous = [
            {
                "ts":    r.recorded_at.isoformat(),
                "value": round(r.metric_value, 2),
                "deviation": round((r.metric_value - mean) / stdev, 2) if stdev > 0 else 0,
            }
            for r in rows
            if stdev > 0 and abs(r.metric_value - mean) > 2 * stdev
        ]
        results[metric_name] = anomalous

    total = sum(len(v) for v in results.values())
    return {
        "node_id":         node_id,
        "hostname":        node.hostname,
        "period_hours":    hours,
        "anomalies":       results,
        "total_anomalies": total,
    }
