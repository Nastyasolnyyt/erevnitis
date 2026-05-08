"""
test_unit_security.py
Модульные тесты: модуль безопасности (security.py)
Проверяют JWT, хеширование паролей, RBAC — изолированно от БД и HTTP
"""
import pytest
from datetime import timedelta
from fastapi import HTTPException

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.security import (
    get_password_hash, verify_password,
    create_access_token, decode_token,
    require_role
)


class TestPasswordHashing:
    """Тесты хеширования паролей (bcrypt)"""

    def test_hash_is_not_plaintext(self):
        """Пароль не хранится в открытом виде"""
        hashed = get_password_hash("secret123")
        assert hashed != "secret123"

    def test_verify_correct_password(self):
        """Верный пароль проходит проверку"""
        hashed = get_password_hash("mypassword")
        assert verify_password("mypassword", hashed) is True

    def test_reject_wrong_password(self):
        """Неверный пароль отклоняется"""
        hashed = get_password_hash("correct")
        assert verify_password("wrong", hashed) is False

    def test_different_hashes_same_password(self):
        """Одинаковые пароли дают разные хеши (соль)"""
        h1 = get_password_hash("same")
        h2 = get_password_hash("same")
        assert h1 != h2  # bcrypt использует случайную соль


class TestJWT:
    """Тесты JWT токенов"""

    def test_create_and_decode_token(self):
        """Токен создаётся и декодируется корректно"""
        token = create_access_token({"sub": "testuser", "role": "admin"})
        data = decode_token(token)
        assert data.username == "testuser"
        assert data.role == "admin"

    def test_invalid_token_raises_401(self):
        """Поддельный токен вызывает HTTP 401"""
        with pytest.raises(HTTPException) as exc_info:
            decode_token("this.is.fake")
        assert exc_info.value.status_code == 401

    def test_expired_token_raises_401(self):
        """Просроченный токен вызывает HTTP 401"""
        token = create_access_token(
            {"sub": "user", "role": "viewer"},
            expires_delta=timedelta(seconds=-1)  # уже истёк
        )
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401

    def test_token_contains_role(self):
        """Роль сохраняется в payload токена"""
        for role in ["admin", "sre", "viewer"]:
            token = create_access_token({"sub": "u", "role": role})
            data = decode_token(token)
            assert data.role == role

    def test_empty_subject_raises_401(self):
        """Токен без sub поля отклоняется"""
        token = create_access_token({"role": "admin"})  # нет sub
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401


class TestRBAC:
    """Тесты системы контроля доступа (RBAC)"""

    def test_require_role_factory_creates_checker(self):
        """Фабрика require_role возвращает функцию-зависимость"""
        checker = require_role("admin")
        assert callable(checker)

    def test_role_not_in_allowed_raises_403(self):
        """Неподходящая роль вызывает HTTP 403"""
        from app.core.security import TokenData
        checker = require_role("admin")
        token_data = TokenData(username="user", role="viewer")
        with pytest.raises(HTTPException) as exc_info:
            checker(token_data)
        assert exc_info.value.status_code == 403

    def test_allowed_role_passes(self):
        """Подходящая роль пропускается без ошибки"""
        from app.core.security import TokenData
        checker = require_role("admin", "sre")
        token_data = TokenData(username="engineer", role="sre")
        result = checker(token_data)
        assert result.username == "engineer"

    def test_admin_passes_admin_check(self):
        """Администратор проходит проверку admin"""
        from app.core.security import TokenData
        checker = require_role("admin")
        result = checker(TokenData(username="admin", role="admin"))
        assert result is not None
