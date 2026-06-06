from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class MetricHistory(Base):
    __tablename__ = "metrics_history"
    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(Integer, ForeignKey("nodes.id", ondelete="CASCADE"), nullable=False)
    metric_name = Column(String(50), nullable=False)
    metric_value = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    node = relationship("Node", back_populates="metrics")
    __table_args__ = (
        Index("ix_metrics_node_name_time", "node_id", "metric_name", "recorded_at"),
    )
