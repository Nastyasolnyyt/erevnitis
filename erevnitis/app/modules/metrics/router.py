from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import io, csv

from app.core.database import get_db
from app.core.security import require_admin, require_any_auth
from app.modules.metrics.models import MetricHistory
from app.modules.nodes.models import Node

router = APIRouter()

KNOWN_METRICS = ["cpu_usage", "ram_utilization", "disk_free", "net_rx_mb", "net_tx_mb", "uptime_hours"]

class MetricWrite(BaseModel):
    node_id: int
    metric_name: str
    metric_value: float
    recorded_at: Optional[datetime] = None

class MetricBulkWrite(BaseModel):
    metrics: List[MetricWrite]

@router.post("/", status_code=201)
def write_metric(data: MetricWrite, db: Session = Depends(get_db)):
    node = db.query(Node).filter(Node.id == data.node_id).first()
    if not node:
        raise HTTPException(404, "Узел не найден")
    m = MetricHistory(node_id=data.node_id, metric_name=data.metric_name,
                      metric_value=data.metric_value, recorded_at=data.recorded_at or datetime.utcnow())
    db.add(m)
    node.last_seen = datetime.utcnow()
    node.status = True
    db.commit()
    return {"id": m.id}

@router.post("/bulk", status_code=201)
def write_metrics_bulk(data: MetricBulkWrite, db: Session = Depends(get_db)):
    now = datetime.utcnow()
    node_ids = set(m.node_id for m in data.metrics)
    existing = {n.id for n in db.query(Node.id).filter(Node.id.in_(node_ids)).all()}
    objects = []
    for m in data.metrics:
        if m.node_id not in existing:
            continue
        objects.append(MetricHistory(node_id=m.node_id, metric_name=m.metric_name,
                                     metric_value=m.metric_value, recorded_at=m.recorded_at or now))
    db.bulk_save_objects(objects)
    db.query(Node).filter(Node.id.in_(existing)).update(
        {"last_seen": now, "status": True}, synchronize_session=False)
    db.commit()
    return {"written": len(objects)}

@router.get("/node/{node_id}/summary")
def get_node_summary(node_id: int, db: Session = Depends(get_db), _=Depends(require_any_auth)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(404, "Узел не найден")
    result = {"node_id": node_id, "hostname": node.hostname, "last_updated": None}
    last_time = None
    for mn in KNOWN_METRICS:
        row = (db.query(MetricHistory)
               .filter(MetricHistory.node_id == node_id, MetricHistory.metric_name == mn)
               .order_by(desc(MetricHistory.recorded_at)).first())
        if row:
            result[mn] = round(row.metric_value, 2)
            if last_time is None or row.recorded_at > last_time:
                last_time = row.recorded_at
        else:
            result[mn] = None
    result["last_updated"] = last_time.isoformat() if last_time else None
    return result

@router.get("/node/{node_id}/all-series")
def get_all_series(node_id: int, hours: int = Query(24, ge=1, le=720),
                   db: Session = Depends(get_db), _=Depends(require_any_auth)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(404, "Узел не найден")
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = (db.query(MetricHistory)
            .filter(MetricHistory.node_id == node_id, MetricHistory.recorded_at >= since)
            .order_by(MetricHistory.recorded_at).all())
    series = {}
    for r in rows:
        if r.metric_name not in series:
            series[r.metric_name] = []
        series[r.metric_name].append({"ts": r.recorded_at.isoformat(), "value": round(r.metric_value, 2)})
    return {"node_id": node_id, "hostname": node.hostname, "series": series}

@router.get("/node/{node_id}/agent-script")
def get_agent_script(node_id: int, db: Session = Depends(get_db), _=Depends(require_any_auth)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(404, "Узел не найден")
    script = f"""#!/bin/bash
# Erevnitis Agent для {node.hostname} (node_id={node_id})
# Установка: chmod +x agent.sh && nohup ./agent.sh &
# Или добавь в cron: * * * * * /path/to/agent.sh

EREVNITIS_URL="${{EREVNITIS_URL:-http://YOUR_SERVER:8000}}"
NODE_ID={node_id}
INTERVAL=60

collect_and_send() {{
  CPU=$(top -bn1 | grep "Cpu(s)" | awk '{{print $2}}' | sed 's/%us,//' | tr -d ' %' 2>/dev/null || echo 0)
  RAM=$(free | awk '/Mem/ {{printf "%.1f", ($3/$2)*100}}' 2>/dev/null || echo 0)
  DISK=$(df / | awk 'NR==2 {{printf "%.1f", 100-$5}}' 2>/dev/null || echo 0)
  UPTIME=$(awk '{{print int($1/3600)}}' /proc/uptime 2>/dev/null || echo 0)
  RX1=$(cat /sys/class/net/$(ip route | awk '/default/{{print $5}}')/statistics/rx_bytes 2>/dev/null || echo 0)
  sleep 1
  RX2=$(cat /sys/class/net/$(ip route | awk '/default/{{print $5}}')/statistics/rx_bytes 2>/dev/null || echo 0)
  NET_RX=$(echo "scale=3; ($RX2-$RX1)/1048576" | bc 2>/dev/null || echo 0)

  curl -s -X POST "$EREVNITIS_URL/api/v1/metrics/bulk" \\
    -H "Content-Type: application/json" \\
    -d '{{"metrics": [
      {{"node_id": '$NODE_ID', "metric_name": "cpu_usage",      "metric_value": '$CPU'}},
      {{"node_id": '$NODE_ID', "metric_name": "ram_utilization", "metric_value": '$RAM'}},
      {{"node_id": '$NODE_ID', "metric_name": "disk_free",       "metric_value": '$DISK'}},
      {{"node_id": '$NODE_ID', "metric_name": "net_rx_mb",       "metric_value": '$NET_RX'}},
      {{"node_id": '$NODE_ID', "metric_name": "uptime_hours",    "metric_value": '$UPTIME'}}
    ]}}' > /dev/null 2>&1
}}

echo "Erevnitis Agent запущен для {node.hostname} (ID={node_id})"
while true; do
  collect_and_send
  sleep $INTERVAL
done
"""
    return PlainTextResponse(content=script,
        headers={{"Content-Disposition": f"attachment; filename=erevnitis_agent_{node_id}.sh"}})

@router.get("/node/{node_id}/export/csv")
def export_csv(node_id: int, hours: int = Query(168), db: Session = Depends(get_db), _=Depends(require_any_auth)):
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(404, "Узел не найден")
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = (db.query(MetricHistory)
            .filter(MetricHistory.node_id == node_id, MetricHistory.recorded_at >= since)
            .order_by(MetricHistory.recorded_at).all())
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["node_id", "hostname", "metric_name", "metric_value", "recorded_at"])
    for r in rows:
        w.writerow([r.node_id, node.hostname, r.metric_name, r.metric_value, r.recorded_at.isoformat()])
    output.seek(0)
    return StreamingResponse(io.StringIO(output.getvalue()), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=metrics_{node.hostname}.csv"})

@router.delete("/node/{node_id}/old")
def delete_old(node_id: int, days: int = Query(30, ge=1), db: Session = Depends(get_db), _=Depends(require_admin)):
    cutoff = datetime.utcnow() - timedelta(days=days)
    deleted = db.query(MetricHistory).filter(MetricHistory.node_id == node_id,
                                              MetricHistory.recorded_at < cutoff).delete()
    db.commit()
    return {"deleted_rows": deleted}
