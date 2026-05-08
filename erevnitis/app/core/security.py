"""
Security module - JWT + bcrypt (без passlib)
SINGLE RESPONSIBILITY: только аутентификация/авторизация
"""
from datetime import datetime, timedelta
from typing import Optional
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

# Конфигурация
SECRET_KEY = "erevnitis-secret-key-change-in-production-2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 часа

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None


def get_password_hash(password: str) -> str:
    """Хеширование пароля через bcrypt напрямую"""
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверка пароля через bcrypt напрямую"""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Создание JWT токена"""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> TokenData:
    """Декодирование и валидация JWT"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Неверные учетные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None:
            raise credentials_exception
        return TokenData(username=username, role=role)
    except JWTError:
        raise credentials_exception


def get_current_user_data(token: str = Depends(oauth2_scheme)) -> TokenData:
    """Получить данные текущего пользователя из JWT"""
    return decode_token(token)


def require_role(*allowed_roles: str):
    """
    Фабрика зависимостей для RBAC.
    Использование: Depends(require_role("admin", "sre"))
    """
    def role_checker(token_data: TokenData = Depends(get_current_user_data)) -> TokenData:
        if token_data.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Доступ запрещён. Требуется роль: {', '.join(allowed_roles)}"
            )
        return token_data
    return role_checker


# Удобные готовые зависимости (DRY)
require_admin = require_role("admin")
require_sre_or_admin = require_role("admin", "sre")
require_any_auth = require_role("admin", "sre", "viewer")