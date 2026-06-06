from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import random, math

def seed_database(db: Session):
    # Import here to ensure all models registered
    from app.modules.auth.models import User
    from app.modules.nodes.models import Node
    from app.modules.incidents.models import Incident
    from app.modules.metrics.models import MetricHistory
    from app.modules.audit.models import AuditLog
    from app.core.security import get_password_hash

    if db.query(User).count() > 0:
        return

    users = [
        User(username="admin", email="admin@erevnitis.io",
             hashed_password=get_password_hash("admin123"), role="admin", is_active=True),
        User(username="sre_ivanov", email="ivanov@erevnitis.io",
             hashed_password=get_password_hash("sre123"), role="sre", is_active=True),
        User(username="analyst_smith", email="smith@erevnitis.io",
             hashed_password=get_password_hash("analyst123"), role="analyst", is_active=True),
        User(username="viewer_guest", email="guest@erevnitis.io",
             hashed_password=get_password_hash("view123"), role="viewer", is_active=True),
    ]
    for u in users: db.add(u)
    db.commit()

    nodes_raw = [
        {"hostname": "prod-web-01",    "ip_address": "10.0.1.10", "os_type": "linux",
         "location": "DC-Moscow-1", "purpose": "prod_web_exporter",    "status": True,  "tags": "env:prod,service:web"},
        {"hostname": "prod-db-01",     "ip_address": "10.0.1.20", "os_type": "linux",
         "location": "DC-Moscow-1", "purpose": "prod_db_exporter",     "status": True,  "tags": "env:prod,service:db"},
        {"hostname": "prod-api-01",    "ip_address": "10.0.1.30", "os_type": "linux",
         "location": "DC-Moscow-2", "purpose": "prod_api_exporter",    "status": True,  "tags": "env:prod,service:api"},
        {"hostname": "staging-web-01", "ip_address": "10.0.2.10", "os_type": "linux",
         "location": "DC-Moscow-2", "purpose": "staging_web_exporter", "status": False, "tags": "env:staging,service:web"},
        {"hostname": "monitoring-01",  "ip_address": "10.0.1.50", "os_type": "linux",
         "location": "DC-Moscow-1", "purpose": "monitoring_exporter",  "status": True,  "tags": "env:prod,service:monitoring"},
    ]
    node_objs = []
    for nd in nodes_raw:
        n = Node(**nd)
        db.add(n)
        node_objs.append(n)
    db.commit()
    for n in node_objs: db.refresh(n)

    sre = db.query(User).filter(User.username == "sre_ivanov").first()
    adm = db.query(User).filter(User.username == "admin").first()
    for d in [
        {"title": "HIGH CPU на prod-web-01", "description": "CPU >90% 15 минут",
         "severity": "critical", "status": "open",
         "node_id": node_objs[0].id, "assigned_to_id": sre.id,
         "created_at": datetime.utcnow() - timedelta(hours=2)},
        {"title": "Диск заполнен 95% на prod-db-01", "description": "Свободно <5%",
         "severity": "high", "status": "investigating",
         "node_id": node_objs[1].id, "assigned_to_id": sre.id,
         "created_at": datetime.utcnow() - timedelta(hours=5)},
        {"title": "Недоступность staging-web-01",
         "severity": "medium", "status": "resolved",
         "node_id": node_objs[3].id, "assigned_to_id": adm.id,
         "created_at": datetime.utcnow() - timedelta(days=1),
         "resolved_at": datetime.utcnow() - timedelta(hours=20)},
        {"title": "Высокая latency API p95>500ms",
         "severity": "low", "status": "open",
         "node_id": node_objs[2].id,
         "created_at": datetime.utcnow() - timedelta(minutes=30)},
    ]: db.add(Incident(**d))
    db.commit()

    random.seed(42)
    now = datetime.utcnow()
    profiles = {
        node_objs[0].id: {"cpu": 55, "ram": 62, "disk_used": 68},
        node_objs[1].id: {"cpu": 35, "ram": 81, "disk_used": 89},
        node_objs[2].id: {"cpu": 40, "ram": 57, "disk_used": 45},
        node_objs[4].id: {"cpu": 28, "ram": 44, "disk_used": 52},
    }
    bulk = []
    for node_id, p in profiles.items():
        t = now - timedelta(days=7)
        step = 0
        while t <= now:
            h = t.hour
            day_f = max(0.15, 0.5 + 0.5 * math.sin((h - 6) * math.pi / 12)) if 6 <= h <= 22 else 0.15
            cpu  = min(99, max(1,  p["cpu"]  * day_f + random.uniform(-4, 4)))
            ram  = min(99, max(10, p["ram"]  + random.uniform(-3, 3)))
            disk = min(99, max(5,  p["disk_used"] + step * 0.0001))
            net  = max(0, random.uniform(0, 30) * day_f)
            if node_id == node_objs[0].id and t >= now - timedelta(hours=2):
                cpu = min(99, 88 + random.uniform(-3, 5))
            uptime = (t - (now - timedelta(days=7))).total_seconds() / 3600
            for mn, mv in [("cpu_usage", cpu), ("ram_utilization", ram),
                           ("disk_free", 100-disk), ("net_rx_mb", net),
                           ("uptime_hours", uptime)]:
                bulk.append(MetricHistory(node_id=node_id, metric_name=mn,
                                          metric_value=round(mv, 2), recorded_at=t))
            t += timedelta(minutes=5)
            step += 1
    db.bulk_save_objects(bulk)

    for e in [
        AuditLog(user_id=adm.id, action="CREATE", resource_type="node",
                 resource_id=node_objs[0].id, details='{"hostname":"prod-web-01"}',
                 created_at=datetime.utcnow()-timedelta(days=7)),
        AuditLog(user_id=sre.id, action="UPDATE", resource_type="incident",
                 resource_id=2, details='{"status":{"before":"open","after":"investigating"}}',
                 created_at=datetime.utcnow()-timedelta(hours=4)),
    ]: db.add(e)
    db.commit()
    print(f"✅ Seed complete: {len(bulk)} metric points")
