from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from app.core.database import get_db
from app.core.security import require_admin

router = APIRouter()

class AuditResponse(BaseModel):
    id: int
    user_id: Optional[int]
    action: str
    resource_type: str
    resource_id: Optional[int]
    details: Optional[str]
    ip_address: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True

@router.get("/", response_model=list[AuditResponse])
def list_audit(resource_type: Optional[str] = None, action: Optional[str] = None,
               limit: int = Query(100, le=500), db: Session = Depends(get_db), _=Depends(require_admin)):
    from app.modules.audit.models import AuditLog
    q = db.query(AuditLog).order_by(AuditLog.created_at.desc())
    if resource_type:
        q = q.filter(AuditLog.resource_type == resource_type)
    if action:
        q = q.filter(AuditLog.action == action)
    return q.limit(limit).all()
