"""
test_integration_nodes.py
Интеграционные тесты: модуль управления узлами (Nodes)
Проверяют все CRUD операции и RBAC
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests.conftest import auth_header


NEW_NODE = {
    "hostname": "new-server-01",
    "ip_address": "10.10.10.1",
    "os_type": "linux",
    "location": "DC-Test",
    "purpose": "API Server",
    "tags": "env:test,service:api"
}


class TestNodeRead:
    """Тесты чтения узлов (GET)"""

    def test_list_nodes_authenticated(self, client, viewer_token):
        """Любой авторизованный пользователь видит список узлов"""
        resp = client.get("/api/v1/nodes/", headers=auth_header(viewer_token))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) >= 1

    def test_list_nodes_unauthenticated(self, client):
        """Без токена → 401"""
        resp = client.get("/api/v1/nodes/")
        assert resp.status_code == 401

    def test_get_node_by_id(self, client, viewer_token):
        """Получение узла по ID"""
        resp = client.get("/api/v1/nodes/1", headers=auth_header(viewer_token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 1
        assert "hostname" in body
        assert "ip_address" in body
        assert "status" in body

    def test_get_nonexistent_node(self, client, admin_token):
        """Несуществующий ID → 404"""
        resp = client.get("/api/v1/nodes/9999", headers=auth_header(admin_token))
        assert resp.status_code == 404

    def test_filter_nodes_by_status(self, client, viewer_token):
        """Фильтрация по статусу (online)"""
        resp = client.get("/api/v1/nodes/?status=true",
                          headers=auth_header(viewer_token))
        assert resp.status_code == 200
        for node in resp.json():
            assert node["status"] is True

    def test_nodes_summary_stats(self, client, viewer_token):
        """Статистика узлов возвращает правильную структуру"""
        resp = client.get("/api/v1/nodes/stats/summary",
                          headers=auth_header(viewer_token))
        assert resp.status_code == 200
        body = resp.json()
        assert "total" in body
        assert "online" in body
        assert "offline" in body
        assert body["total"] == body["online"] + body["offline"]


class TestNodeCreate:
    """Тесты создания узлов (POST)"""

    def test_admin_can_create_node(self, client, admin_token):
        """Администратор может создать узел"""
        resp = client.post("/api/v1/nodes/", headers=auth_header(admin_token),
                           json=NEW_NODE)
        assert resp.status_code == 201
        body = resp.json()
        assert body["hostname"] == NEW_NODE["hostname"]
        assert body["ip_address"] == NEW_NODE["ip_address"]
        assert body["status"] is True  # по умолчанию online
        assert "id" in body

    def test_sre_can_create_node(self, client, sre_token):
        """SRE-инженер может создать узел"""
        resp = client.post("/api/v1/nodes/", headers=auth_header(sre_token),
                           json={**NEW_NODE, "hostname": "sre-node", "ip_address": "10.10.10.2"})
        assert resp.status_code == 201

    def test_viewer_cannot_create_node(self, client, viewer_token):
        """Viewer не может создавать узлы → 403"""
        resp = client.post("/api/v1/nodes/", headers=auth_header(viewer_token),
                           json=NEW_NODE)
        assert resp.status_code == 403

    def test_duplicate_ip_rejected(self, client, admin_token):
        """Дублирующийся IP отклоняется → 400"""
        client.post("/api/v1/nodes/", headers=auth_header(admin_token), json=NEW_NODE)
        resp = client.post("/api/v1/nodes/", headers=auth_header(admin_token),
                           json={**NEW_NODE, "hostname": "other-host"})
        assert resp.status_code == 400

    def test_duplicate_hostname_rejected(self, client, admin_token):
        """Дублирующийся hostname отклоняется → 400"""
        client.post("/api/v1/nodes/", headers=auth_header(admin_token), json=NEW_NODE)
        resp = client.post("/api/v1/nodes/", headers=auth_header(admin_token),
                           json={**NEW_NODE, "ip_address": "10.10.10.99"})
        assert resp.status_code == 400

    def test_create_node_missing_required_fields(self, client, admin_token):
        """Отсутствие обязательных полей → 422"""
        resp = client.post("/api/v1/nodes/", headers=auth_header(admin_token),
                           json={"hostname": "incomplete"})
        assert resp.status_code == 422


class TestNodeUpdate:
    """Тесты обновления узлов (PATCH)"""

    def test_admin_can_update_node(self, client, admin_token):
        """Администратор может обновить узел"""
        resp = client.patch("/api/v1/nodes/1", headers=auth_header(admin_token),
                            json={"purpose": "Updated Purpose", "status": False})
        assert resp.status_code == 200
        body = resp.json()
        assert body["purpose"] == "Updated Purpose"
        assert body["status"] is False

    def test_sre_can_update_node(self, client, sre_token):
        """SRE может обновлять узлы"""
        resp = client.patch("/api/v1/nodes/1", headers=auth_header(sre_token),
                            json={"tags": "env:prod,updated:true"})
        assert resp.status_code == 200

    def test_viewer_cannot_update_node(self, client, viewer_token):
        """Viewer не может обновлять узлы → 403"""
        resp = client.patch("/api/v1/nodes/1", headers=auth_header(viewer_token),
                            json={"status": False})
        assert resp.status_code == 403

    def test_partial_update_only_changes_given_fields(self, client, admin_token):
        """PATCH обновляет только переданные поля"""
        original = client.get("/api/v1/nodes/1", headers=auth_header(admin_token)).json()
        client.patch("/api/v1/nodes/1", headers=auth_header(admin_token),
                     json={"purpose": "New Purpose"})
        updated = client.get("/api/v1/nodes/1", headers=auth_header(admin_token)).json()
        assert updated["purpose"] == "New Purpose"
        assert updated["hostname"] == original["hostname"]  # не изменился


class TestNodeDelete:
    """Тесты удаления узлов (DELETE)"""

    def test_admin_can_delete_node(self, client, admin_token):
        """Администратор может удалить узел"""
        # Создаём узел для удаления
        create_resp = client.post("/api/v1/nodes/", headers=auth_header(admin_token),
                                  json=NEW_NODE)
        node_id = create_resp.json()["id"]
        resp = client.delete(f"/api/v1/nodes/{node_id}", headers=auth_header(admin_token))
        assert resp.status_code == 204

    def test_sre_cannot_delete_node(self, client, sre_token):
        """SRE не может удалять узлы → 403"""
        resp = client.delete("/api/v1/nodes/1", headers=auth_header(sre_token))
        assert resp.status_code == 403

    def test_delete_nonexistent_node(self, client, admin_token):
        """Удаление несуществующего узла → 404"""
        resp = client.delete("/api/v1/nodes/9999", headers=auth_header(admin_token))
        assert resp.status_code == 404

    def test_deleted_node_not_accessible(self, client, admin_token):
        """После удаления узел недоступен"""
        create_resp = client.post("/api/v1/nodes/", headers=auth_header(admin_token),
                                  json={**NEW_NODE, "ip_address": "10.20.20.1"})
        node_id = create_resp.json()["id"]
        client.delete(f"/api/v1/nodes/{node_id}", headers=auth_header(admin_token))
        get_resp = client.get(f"/api/v1/nodes/{node_id}", headers=auth_header(admin_token))
        assert get_resp.status_code == 404
