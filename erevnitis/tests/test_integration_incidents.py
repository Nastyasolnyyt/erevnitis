"""
test_integration_incidents.py
Интеграционные тесты: модуль управления инцидентами
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests.conftest import auth_header


NEW_INCIDENT = {
    "title": "Тестовый инцидент",
    "description": "CPU нагрузка >90%",
    "severity": "high",
    "node_id": 1
}


class TestIncidentRead:
    """Тесты чтения инцидентов"""

    def test_list_incidents_authenticated(self, client, viewer_token):
        """Авторизованный пользователь видит список инцидентов"""
        resp = client.get("/api/v1/incidents/", headers=auth_header(viewer_token))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_incidents_unauthenticated(self, client):
        """Без токена → 401"""
        resp = client.get("/api/v1/incidents/")
        assert resp.status_code == 401

    def test_get_incident_by_id(self, client, viewer_token):
        """Получение инцидента по ID"""
        resp = client.get("/api/v1/incidents/1", headers=auth_header(viewer_token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 1
        assert "title" in body
        assert "severity" in body
        assert "status" in body

    def test_get_nonexistent_incident(self, client, admin_token):
        """Несуществующий инцидент → 404"""
        resp = client.get("/api/v1/incidents/9999", headers=auth_header(admin_token))
        assert resp.status_code == 404

    def test_filter_by_status(self, client, viewer_token):
        """Фильтрация по статусу"""
        resp = client.get("/api/v1/incidents/?status=open",
                          headers=auth_header(viewer_token))
        assert resp.status_code == 200
        for inc in resp.json():
            assert inc["status"] == "open"

    def test_incidents_summary_stats(self, client, viewer_token):
        """Статистика инцидентов"""
        resp = client.get("/api/v1/incidents/stats/summary",
                          headers=auth_header(viewer_token))
        assert resp.status_code == 200
        body = resp.json()
        for key in ["total", "open", "investigating", "resolved", "critical"]:
            assert key in body


class TestIncidentCreate:
    """Тесты создания инцидентов"""

    def test_admin_can_create_incident(self, client, admin_token):
        """Администратор создаёт инцидент"""
        resp = client.post("/api/v1/incidents/", headers=auth_header(admin_token),
                           json=NEW_INCIDENT)
        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == NEW_INCIDENT["title"]
        assert body["severity"] == "high"
        assert body["status"] == "open"
        assert "id" in body

    def test_sre_can_create_incident(self, client, sre_token):
        """SRE создаёт инцидент"""
        resp = client.post("/api/v1/incidents/", headers=auth_header(sre_token),
                           json=NEW_INCIDENT)
        assert resp.status_code == 201

    def test_viewer_cannot_create_incident(self, client, viewer_token):
        """Viewer не может создавать инциденты → 403"""
        resp = client.post("/api/v1/incidents/", headers=auth_header(viewer_token),
                           json=NEW_INCIDENT)
        assert resp.status_code == 403

    def test_create_incident_without_node(self, client, admin_token):
        """Инцидент можно создать без привязки к узлу"""
        resp = client.post("/api/v1/incidents/", headers=auth_header(admin_token),
                           json={"title": "Generic incident", "severity": "low"})
        assert resp.status_code == 201
        assert resp.json()["node_id"] is None

    def test_default_severity_is_medium(self, client, admin_token):
        """По умолчанию severity = medium"""
        resp = client.post("/api/v1/incidents/", headers=auth_header(admin_token),
                           json={"title": "Default severity test"})
        assert resp.status_code == 201
        assert resp.json()["severity"] == "medium"


class TestIncidentUpdate:
    """Тесты обновления инцидентов"""

    def test_update_status_to_investigating(self, client, sre_token):
        """SRE меняет статус на 'investigating'"""
        resp = client.patch("/api/v1/incidents/1", headers=auth_header(sre_token),
                            json={"status": "investigating"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "investigating"

    def test_resolve_incident_sets_resolved_at(self, client, admin_token):
        """При переводе в 'resolved' автоматически ставится resolved_at"""
        resp = client.patch("/api/v1/incidents/1", headers=auth_header(admin_token),
                            json={"status": "resolved"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "resolved"
        assert body["resolved_at"] is not None

    def test_viewer_cannot_update_incident(self, client, viewer_token):
        """Viewer не может обновлять инциденты → 403"""
        resp = client.patch("/api/v1/incidents/1", headers=auth_header(viewer_token),
                            json={"status": "resolved"})
        assert resp.status_code == 403


class TestIncidentDelete:
    """Тесты удаления инцидентов"""

    def test_admin_can_delete_incident(self, client, admin_token):
        """Администратор может удалить инцидент"""
        create_resp = client.post("/api/v1/incidents/", headers=auth_header(admin_token),
                                  json=NEW_INCIDENT)
        inc_id = create_resp.json()["id"]
        resp = client.delete(f"/api/v1/incidents/{inc_id}", headers=auth_header(admin_token))
        assert resp.status_code == 204

    def test_sre_cannot_delete_incident(self, client, sre_token):
        """SRE не может удалять инциденты → 403"""
        resp = client.delete("/api/v1/incidents/1", headers=auth_header(sre_token))
        assert resp.status_code == 403

    def test_deleted_incident_not_found(self, client, admin_token):
        """После удаления инцидент недоступен"""
        create_resp = client.post("/api/v1/incidents/", headers=auth_header(admin_token),
                                  json={"title": "To be deleted", "severity": "low"})
        inc_id = create_resp.json()["id"]
        client.delete(f"/api/v1/incidents/{inc_id}", headers=auth_header(admin_token))
        get_resp = client.get(f"/api/v1/incidents/{inc_id}", headers=auth_header(admin_token))
        assert get_resp.status_code == 404


class TestAlertmanagerWebhook:
    """Тесты автоматического создания инцидентов из Prometheus webhook"""

    def test_webhook_creates_incident(self, client):
        """Webhook от Alertmanager создаёт инцидент автоматически"""
        payload = {
            "alerts": [{
                "labels": {"alertname": "HighCPU", "severity": "critical",
                           "instance": "prod-web-01"},
                "annotations": {"description": "CPU > 90% на prod-web-01"}
            }]
        }
        resp = client.post("/api/v1/incidents/webhook/alertmanager", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert "[AUTO]" in body["title"]
        assert body["severity"] == "critical"
        assert body["status"] == "open"

    def test_webhook_maps_warning_to_high(self, client):
        """severity=warning маппится в high"""
        payload = {
            "alerts": [{
                "labels": {"alertname": "DiskFull", "severity": "warning"},
                "annotations": {"summary": "Диск почти заполнен"}
            }]
        }
        resp = client.post("/api/v1/incidents/webhook/alertmanager", json=payload)
        assert resp.status_code == 201
        assert resp.json()["severity"] == "high"

    def test_webhook_empty_alerts_rejected(self, client):
        """Пустой список алертов → 400"""
        resp = client.post("/api/v1/incidents/webhook/alertmanager",
                           json={"alerts": []})
        assert resp.status_code == 400
