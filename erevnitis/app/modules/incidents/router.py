"""
Incidents router - CRUD + webhook receiver
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from app.core.database import get_db
from app.core.security import require_admin, require_sre_or_admin, require_any_auth
from app.modules.incidents.models import Incident
from app.modules.incidents.schemas import IncidentCreate, IncidentUpdate, IncidentResponse

router = APIRouter()


@router.get("/", response_model=list[IncidentResponse])
def list_incidents(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    node_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _=Depends(require_any_auth)
):
    """List incidents with optional filters. All authenticated users."""
    query = db.query(Incident)
    if status:
        query = query.filter(Incident.status == status)
    if severity:
        query = query.filter(Incident.severity == severity)
    if node_id:
        query = query.filter(Incident.node_id == node_id)
    return query.order_by(Incident.created_at.desc()).all()


@router.get("/stats/summary")
def incidents_summary(db: Session = Depends(get_db), _=Depends(require_any_auth)):
    """Dashboard stats"""
    total = db.query(Incident).count()
    open_count = db.query(Incident).filter(Incident.status == "open").count()
    investigating = db.query(Incident).filter(Incident.status == "investigating").count()
    resolved = db.query(Incident).filter(Incident.status == "resolved").count()
    critical = db.query(Incident).filter(Incident.severity == "critical",
                                          Incident.status != "resolved").count()
    return {
        "total": total, "open": open_count,
        "investigating": investigating, "resolved": resolved, "critical": critical
    }


@router.get("/{incident_id}", response_model=IncidentResponse)
def get_incident(incident_id: int, db: Session = Depends(get_db), _=Depends(require_any_auth)):
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Инцидент не найден")
    return inc


@router.post("/", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
def create_incident(
    inc_data: IncidentCreate,
    db: Session = Depends(get_db),
    _=Depends(require_sre_or_admin)
):
    """Create incident manually. SRE and Admin."""
    incident = Incident(**inc_data.model_dump())
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


@router.post("/webhook/alertmanager", response_model=IncidentResponse,
             status_code=status.HTTP_201_CREATED)
def receive_alertmanager_webhook(payload: dict, db: Session = Depends(get_db)):
    """
    Receive Prometheus Alertmanager webhook - PUBLIC endpoint.
    Creates incident automatically from alert payload.
    """
    alerts = payload.get("alerts", [])
    if not alerts:
        raise HTTPException(status_code=400, detail="Нет алертов в payload")

    alert = alerts[0]
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})

    severity_map = {"critical": "critical", "warning": "high", "info": "low"}
    severity = severity_map.get(labels.get("severity", "warning"), "medium")

    incident = Incident(
        title=f"[AUTO] {labels.get('alertname', 'Unknown Alert')}",
        description=annotations.get("description", annotations.get("summary", "Автоматически создан из алерта")),
        severity=severity,
        status="open",
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


@router.patch("/{incident_id}", response_model=IncidentResponse)
def update_incident(
    incident_id: int,
    inc_data: IncidentUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_sre_or_admin)
):
    """Update incident. SRE and Admin."""
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Инцидент не найден")

    update_data = inc_data.model_dump(exclude_unset=True)

    # Auto-set resolved_at when status changes to resolved
    if update_data.get("status") == "resolved" and inc.status != "resolved":
        update_data["resolved_at"] = datetime.utcnow()

    for key, value in update_data.items():
        setattr(inc, key, value)
    inc.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(inc)
    return inc


@router.delete("/{incident_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_incident(
    incident_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin)
):
    """Delete incident. Admin only."""
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Инцидент не найден")
    db.delete(inc)
    db.commit()


@router.get("/export/csv")
def export_incidents_csv(
    db: Session = Depends(get_db),
    _=Depends(require_any_auth)
):
    """Экспорт всех инцидентов в CSV"""
    import io, csv
    from fastapi.responses import StreamingResponse
    incidents = db.query(Incident).order_by(Incident.created_at.desc()).all()
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["id","title","severity","status","node_id","assigned_to_id","created_at","resolved_at","description"])
    for inc in incidents:
        w.writerow([inc.id, inc.title, inc.severity, inc.status, inc.node_id,
                    inc.assigned_to_id, inc.created_at, inc.resolved_at, inc.description])
    output.seek(0)
    return StreamingResponse(io.StringIO(output.getvalue()), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=incidents.csv"})
