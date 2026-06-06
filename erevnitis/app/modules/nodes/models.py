from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class Node(Base):
    __tablename__ = "nodes"
    id = Column(Integer, primary_key=True, index=True)
    hostname = Column(String(255), unique=True, index=True, nullable=False)
    ip_address = Column(String(45), unique=True, index=True, nullable=False)
    os_type = Column(String(20), default="linux")
    location = Column(String(100))
    purpose = Column(String(255))   # Pushgateway job name
    status = Column(Boolean, default=True)
    tags = Column(String(500))
    config_path = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    incidents = relationship("Incident", back_populates="node")
    metrics = relationship("MetricHistory", back_populates="node", cascade="all, delete-orphan")
