from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class IncidentCreate(BaseModel):
    title: str
    description: Optional[str] = None
    severity: str = "medium"
    node_id: Optional[int] = None
    assigned_to_id: Optional[int] = None


class IncidentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    node_id: Optional[int] = None
    assigned_to_id: Optional[int] = None


class IncidentResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    severity: str
    status: str
    node_id: Optional[int]
    assigned_to_id: Optional[int]
    created_at: datetime
    updated_at: Optional[datetime]
    resolved_at: Optional[datetime]

    class Config:
        from_attributes = True
