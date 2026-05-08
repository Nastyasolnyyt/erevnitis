"""
Incident model
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    severity = Column(String(20), default="medium")   # critical, high, medium, low
    status = Column(String(20), default="open", index=True)  # open, investigating, resolved
    node_id = Column(Integer, ForeignKey("nodes.id"), nullable=True)
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    # Relationships
    node = relationship("Node", back_populates="incidents")
    assigned_to = relationship("User", back_populates="assigned_incidents",
                                foreign_keys=[assigned_to_id])
