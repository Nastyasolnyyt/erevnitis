"""
conftest.py — общие фикстуры для всех тестов Erevnitis
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Используем отдельную in-memory БД для тестов (изолированность)
TEST_DATABASE_URL = "sqlite:///./test_erevnitis.db"

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.database import Base, get_db
from app.core.security import get_password_hash
from app.main import app

# Тестовый движок
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def db_session():
    """Чистая БД для каждого теста"""
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def client(db_session):
    """Test client с подменённой БД"""
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(bind=test_engine)

    # Создаём тестовых пользователей напрямую
    from app.modules.auth.models import User
    from app.modules.nodes.models import Node
    from app.modules.incidents.models import Incident

    admin = User(username="admin", email="admin@test.com",
                 hashed_password=get_password_hash("admin123"), role="admin", is_active=True)
    sre = User(username="sre_user", email="sre@test.com",
               hashed_password=get_password_hash("sre123"), role="sre", is_active=True)
    viewer = User(username="viewer_user", email="viewer@test.com",
                  hashed_password=get_password_hash("view123"), role="viewer", is_active=True)

    db_session.add_all([admin, sre, viewer])
    db_session.commit()

    node = Node(hostname="test-node-01", ip_address="192.168.1.1",
                os_type="linux", location="DC-Test", purpose="Testing", status=True)
    db_session.add(node)
    db_session.commit()
    db_session.refresh(node)

    incident = Incident(title="Test Incident", description="Test desc",
                        severity="medium", status="open", node_id=node.id)
    db_session.add(incident)
    db_session.commit()

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def admin_token(client):
    """JWT токен администратора"""
    resp = client.post("/api/v1/auth/token",
                       data={"username": "admin", "password": "admin123"})
    return resp.json()["access_token"]


@pytest.fixture
def sre_token(client):
    """JWT токен SRE-инженера"""
    resp = client.post("/api/v1/auth/token",
                       data={"username": "sre_user", "password": "sre123"})
    return resp.json()["access_token"]


@pytest.fixture
def viewer_token(client):
    """JWT токен наблюдателя"""
    resp = client.post("/api/v1/auth/token",
                       data={"username": "viewer_user", "password": "view123"})
    return resp.json()["access_token"]


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
