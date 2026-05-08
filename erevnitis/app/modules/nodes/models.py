"""
Node model - server/infrastructure asset
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class Node(Base):
    __tablename__ = "nodes"

    id = Column(Integer, primary_key=True, index=True)
    hostname = Column(String(255), unique=True, index=True, nullable=False)
    ip_address = Column(String(45), unique=True, index=True, nullable=False)
    os_type = Column(String(20), default="linux")  # linux, windows, bsd
    location = Column(String(100))
    purpose = Column(String(255))
    status = Column(Boolean, default=True)  # True = online, False = offline
    tags = Column(String(500))              # "env:prod,service:web"
    config_path = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)

    # Relationships
    incidents = relationship("Incident", back_populates="node")
