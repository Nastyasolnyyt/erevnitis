from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class Runbook(Base):
    __tablename__ = "runbooks"

    id          = Column(Integer, primary_key=True, index=True)
    title       = Column(String(255), nullable=False)        # "CPU перегружен"
    alert_name  = Column(String(100), nullable=True, index=True)  # "HighCPU" — совпадает с alertname Prometheus
    severity    = Column(String(20),  default="medium")      # critical/high/medium/low
    description = Column(Text, nullable=True)                # краткое описание проблемы
    steps       = Column(Text, nullable=False)               # шаги в JSON: [{"step":1,"action":"..."}]
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)