"""
test_integration_auth.py
Интеграционные тесты: модуль аутентификации
Проверяют HTTP endpoints /api/v1/auth/* с реальной БД (тестовая)
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tests.conftest import auth_header


class TestLogin:
    """Тесты входа (POST /api/v1/auth/token)"""

    def test_login_admin_success(self, client):
        """Успешный вход администратора возвращает JWT"""
        resp = client.post("/api/v1/auth/token",
                           data={"username": "admin", "password": "admin123"})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["role"] == "admin"
        assert body["username"] == "admin"

    def test_login_sre_success(self, client):
        """Успешный вход SRE-инженера"""
        resp = client.post("/api/v1/auth/token",
                           data={"username": "sre_user", "password": "sre123"})
        assert resp.status_code == 200
        assert resp.json()["role"] == "sre"

    def test_login_wrong_password(self, client):
        """Неверный пароль → 401"""
        resp = client.post("/api/v1/auth/token",
                           data={"username": "admin", "password": "wrongpass"})
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client):
        """Несуществующий пользователь → 401"""
        resp = client.post("/api/v1/auth/token",
                           data={"username": "nobody", "password": "123"})
        assert resp.status_code == 401

    def test_login_empty_credentials(self, client):
        """Пустые учётные данные → 422 (Unprocessable Entity)"""
        resp = client.post("/api/v1/auth/token", data={})
        assert resp.status_code == 422


class TestGetMe:
    """Тесты эндпоинта /api/v1/auth/me"""

    def test_get_me_with_valid_token(self, client, admin_token):
        """Авторизованный пользователь получает свои данные"""
        resp = client.get("/api/v1/auth/me", headers=auth_header(admin_token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "admin"
        assert body["role"] == "admin"
        assert "hashed_password" not in body  # пароль не возвращается

    def test_get_me_without_token(self, client):
        """Без токена → 401"""
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    def test_get_me_with_fake_token(self, client):
        """Поддельный токен → 401"""
        resp = client.get("/api/v1/auth/me",
                          headers={"Authorization": "Bearer fake.token.here"})
        assert resp.status_code == 401


class TestUserRegistration:
    """Тесты регистрации пользователей (POST /api/v1/auth/register)"""

    def test_admin_can_register_user(self, client, admin_token):
        """Администратор может создать нового пользователя"""
        resp = client.post("/api/v1/auth/register",
                           headers=auth_header(admin_token),
                           json={"username": "new_sre", "email": "newsre@test.com",
                                 "password": "pass123", "role": "sre"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "new_sre"
        assert body["role"] == "sre"

    def test_sre_cannot_register_user(self, client, sre_token):
        """SRE не может создавать пользователей → 403"""
        resp = client.post("/api/v1/auth/register",
                           headers=auth_header(sre_token),
                           json={"username": "another", "email": "a@test.com",
                                 "password": "pass", "role": "viewer"})
        assert resp.status_code == 403

    def test_viewer_cannot_register_user(self, client, viewer_token):
        """Viewer не может создавать пользователей → 403"""
        resp = client.post("/api/v1/auth/register",
                           headers=auth_header(viewer_token),
                           json={"username": "bad", "email": "bad@test.com",
                                 "password": "pass", "role": "viewer"})
        assert resp.status_code == 403

    def test_duplicate_username_rejected(self, client, admin_token):
        """Дублирующийся username отклоняется → 400"""
        resp = client.post("/api/v1/auth/register",
                           headers=auth_header(admin_token),
                           json={"username": "admin", "email": "other@test.com",
                                 "password": "pass", "role": "viewer"})
        assert resp.status_code == 400

    def test_list_users_admin_only(self, client, admin_token, sre_token):
        """Список пользователей доступен только admin"""
        r1 = client.get("/api/v1/auth/users", headers=auth_header(admin_token))
        assert r1.status_code == 200
        assert isinstance(r1.json(), list)

        r2 = client.get("/api/v1/auth/users", headers=auth_header(sre_token))
        assert r2.status_code == 403
