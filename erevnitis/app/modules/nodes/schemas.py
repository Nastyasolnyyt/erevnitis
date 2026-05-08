from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class NodeCreate(BaseModel):
    hostname: str
    ip_address: str
    os_type: str = "linux"
    location: Optional[str] = None
    purpose: Optional[str] = None
    tags: Optional[str] = None
    config_path: Optional[str] = None


class NodeUpdate(BaseModel):
    hostname: Optional[str] = None
    ip_address: Optional[str] = None
    os_type: Optional[str] = None
    location: Optional[str] = None
    purpose: Optional[str] = None
    status: Optional[bool] = None
    tags: Optional[str] = None
    config_path: Optional[str] = None


class NodeResponse(BaseModel):
    id: int
    hostname: str
    ip_address: str
    os_type: str
    location: Optional[str]
    purpose: Optional[str]
    status: bool
    tags: Optional[str]
    config_path: Optional[str]
    created_at: datetime
    last_seen: Optional[datetime]

    class Config:
        from_attributes = True
