"""
Runbooks router — пошаговые инструкции по устранению инцидентов
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from pydantic import BaseModel
import json

from app.core.database import get_db
from app.core.security import require_admin, require_sre_or_admin, require_any_auth
from app.modules.runbooks.models import Runbook

router = APIRouter()


# ── Pydantic схемы ────────────────────────────────────────────
class RunbookCreate(BaseModel):
    title:       str
    alert_name:  Optional[str] = None
    severity:    str = "medium"
    description: Optional[str] = None
    steps:       list  # список шагов: [{"step": 1, "action": "..."}]


class RunbookUpdate(BaseModel):
    title:       Optional[str] = None
    alert_name:  Optional[str] = None
    severity:    Optional[str] = None
    description: Optional[str] = None
    steps:       Optional[list] = None


class RunbookResponse(BaseModel):
    id:          int
    title:       str
    alert_name:  Optional[str]
    severity:    str
    description: Optional[str]
    steps:       list
    created_at:  datetime
    updated_at:  Optional[datetime]

    class Config:
        from_attributes = True

    @classmethod
    def from_orm(cls, obj):
        data = {
            "id":          obj.id,
            "title":       obj.title,
            "alert_name":  obj.alert_name,
            "severity":    obj.severity,
            "description": obj.description,
            "steps":       json.loads(obj.steps) if isinstance(obj.steps, str) else obj.steps,
            "created_at":  obj.created_at,
            "updated_at":  obj.updated_at,
        }
        return cls(**data)


# ── Эндпоинты ─────────────────────────────────────────────────

@router.get("/", response_model=list[RunbookResponse])
def list_runbooks(
    severity:   Optional[str] = None,
    alert_name: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(require_any_auth)
):
    """Список всех runbook-ов. Доступен всем авторизованным."""
    q = db.query(Runbook)
    if severity:
        q = q.filter(Runbook.severity == severity)
    if alert_name:
        q = q.filter(Runbook.alert_name == alert_name)
    books = q.order_by(Runbook.severity, Runbook.title).all()
    return [RunbookResponse.from_orm(b) for b in books]


@router.get("/{runbook_id}", response_model=RunbookResponse)
def get_runbook(
    runbook_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_any_auth)
):
    book = db.query(Runbook).filter(Runbook.id == runbook_id).first()
    if not book:
        raise HTTPException(404, "Runbook не найден")
    return RunbookResponse.from_orm(book)


@router.get("/by-alert/{alert_name}", response_model=RunbookResponse)
def get_runbook_by_alert(
    alert_name: str,
    db: Session = Depends(get_db),
    _=Depends(require_any_auth)
):
    """Найти runbook по имени алерта Prometheus (используется в карточке инцидента)."""
    book = db.query(Runbook).filter(Runbook.alert_name == alert_name).first()
    if not book:
        raise HTTPException(404, f"Runbook для алерта '{alert_name}' не найден")
    return RunbookResponse.from_orm(book)


@router.post("/", response_model=RunbookResponse, status_code=201)
def create_runbook(
    data: RunbookCreate,
    db: Session = Depends(get_db),
    _=Depends(require_sre_or_admin)
):
    """Создать runbook. Только SRE и Admin."""
    book = Runbook(
        title=data.title,
        alert_name=data.alert_name,
        severity=data.severity,
        description=data.description,
        steps=json.dumps(data.steps, ensure_ascii=False),
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    return RunbookResponse.from_orm(book)


@router.patch("/{runbook_id}", response_model=RunbookResponse)
def update_runbook(
    runbook_id: int,
    data: RunbookUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_sre_or_admin)
):
    book = db.query(Runbook).filter(Runbook.id == runbook_id).first()
    if not book:
        raise HTTPException(404, "Runbook не найден")

    update = data.model_dump(exclude_unset=True)
    if "steps" in update:
        update["steps"] = json.dumps(update["steps"], ensure_ascii=False)
    for k, v in update.items():
        setattr(book, k, v)
    book.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(book)
    return RunbookResponse.from_orm(book)


@router.delete("/{runbook_id}", status_code=204)
def delete_runbook(
    runbook_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin)
):
    """Удалить runbook. Только Admin."""
    book = db.query(Runbook).filter(Runbook.id == runbook_id).first()
    if not book:
        raise HTTPException(404, "Runbook не найден")
    db.delete(book)
    db.commit()