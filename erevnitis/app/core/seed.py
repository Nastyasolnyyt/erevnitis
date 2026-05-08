"""
Seed database with test data
"""
from sqlalchemy.orm import Session
from app.modules.auth.models import User
from app.modules.nodes.models import Node
from app.modules.incidents.models import Incident
from app.core.security import get_password_hash
from datetime import datetime, timedelta
import random


def seed_database(db: Session):
    """Populate DB with test data if empty"""
    if db.query(User).count() > 0:
        return  # Already seeded

    # --- USERS ---
    users = [
        User(username="admin", email="admin@erevnitis.io",
             hashed_password=get_password_hash("admin123"), role="admin", is_active=True),
        User(username="sre_ivanov", email="ivanov@erevnitis.io",
             hashed_password=get_password_hash("sre123"), role="sre", is_active=True),
        User(username="viewer_guest", email="guest@erevnitis.io",
             hashed_password=get_password_hash("view123"), role="viewer", is_active=True),
    ]
    for u in users:
        db.add(u)
    db.commit()

    # --- NODES ---
    nodes_data = [
        {"hostname": "prod-web-01", "ip_address": "10.0.1.10", "os_type": "linux",
         "location": "DC-Moscow-1", "purpose": "Web Frontend", "status": True, "tags": "env:prod,service:web"},
        {"hostname": "prod-db-01", "ip_address": "10.0.1.20", "os_type": "linux",
         "location": "DC-Moscow-1", "purpose": "PostgreSQL Primary", "status": True, "tags": "env:prod,service:db"},
        {"hostname": "prod-api-01", "ip_address": "10.0.1.30", "os_type": "linux",
         "location": "DC-Moscow-2", "purpose": "FastAPI Backend", "status": True, "tags": "env:prod,service:api"},
        {"hostname": "staging-web-01", "ip_address": "10.0.2.10", "os_type": "linux",
         "location": "DC-Moscow-2", "purpose": "Staging Web", "status": False, "tags": "env:staging,service:web"},
        {"hostname": "monitoring-01", "ip_address": "10.0.1.50", "os_type": "linux",
         "location": "DC-Moscow-1", "purpose": "Prometheus + Grafana", "status": True, "tags": "env:prod,service:monitoring"},
    ]
    node_objs = []
    for nd in nodes_data:
        node = Node(**nd)
        db.add(node)
        node_objs.append(node)
    db.commit()
    for n in node_objs:
        db.refresh(n)

    # --- INCIDENTS ---
    sre_user = db.query(User).filter(User.username == "sre_ivanov").first()
    admin_user = db.query(User).filter(User.username == "admin").first()

    incidents_data = [
        {"title": "HIGH CPU на prod-web-01", "description": "CPU загрузка >90% в течение 15 минут",
         "severity": "critical", "status": "open", "node_id": node_objs[0].id,
         "assigned_to_id": sre_user.id, "created_at": datetime.utcnow() - timedelta(hours=2)},
        {"title": "Диск заполнен на 95% на prod-db-01", "description": "Свободно менее 5% дискового пространства",
         "severity": "high", "status": "investigating",
         "node_id": node_objs[1].id, "assigned_to_id": sre_user.id,
         "created_at": datetime.utcnow() - timedelta(hours=5)},
        {"title": "Недоступность staging-web-01", "description": "Сервер не отвечает на ping",
         "severity": "medium", "status": "resolved",
         "node_id": node_objs[3].id, "assigned_to_id": admin_user.id,
         "created_at": datetime.utcnow() - timedelta(days=1),
         "resolved_at": datetime.utcnow() - timedelta(hours=20)},
        {"title": "Высокая latency API", "description": "p95 latency >500ms на /api/v1/nodes",
         "severity": "low", "status": "open",
         "node_id": node_objs[2].id, "assigned_to_id": None,
         "created_at": datetime.utcnow() - timedelta(minutes=30)},
    ]
    for inc_data in incidents_data:
        incident = Incident(**inc_data)
        db.add(incident)
    db.commit()

    print("✅ Database seeded with test data")
