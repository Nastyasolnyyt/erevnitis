# Erevnitis SRE Panel

Система управления инфраструктурой и инцидентами для SRE-команд.  
**Курсовой проект**  
Студент: Солнцева Анастасия Павловна, 241-3211

---

## Структура проекта

```
erevnitis/
├── app/
│   ├── core/
│   │   ├── database.py        # SQLAlchemy: подключение к БД (ЛР2)
│   │   ├── security.py        # JWT + bcrypt + RBAC (ЛР2, ЛР3)
│   │   ├── seed.py            # Тестовые данные (ЛР2)
│   │   └── observability.py   # Логи + метрики производительности (ЛР3)
│   ├── modules/
│   │   ├── auth/              # Аутентификация и управление пользователями
│   │   │   ├── models.py      # User (SQLAlchemy модель)
│   │   │   ├── schemas.py     # Pydantic схемы (UserCreate, UserResponse, Token)
│   │   │   └── router.py      # POST /token, POST /register, GET /me, GET /users
│   │   ├── nodes/             # Управление серверными узлами
│   │   │   ├── models.py      # Node (SQLAlchemy модель)
│   │   │   ├── schemas.py     # NodeCreate, NodeUpdate, NodeResponse
│   │   │   └── router.py      # CRUD + /stats/summary
│   │   └── incidents/         # Управление инцидентами
│   │       ├── models.py      # Incident (SQLAlchemy модель)
│   │       ├── schemas.py     # IncidentCreate, IncidentUpdate, IncidentResponse
│   │       └── router.py      # CRUD + webhook + /stats/summary
│   └── main.py                # Точка входа FastAPI
├── tests/
│   ├── conftest.py            # Фикстуры: тестовая БД, клиент, токены
│   ├── test_unit_security.py  # 13 модульных тестов (bcrypt, JWT, RBAC)
│   ├── test_integration_auth.py      # 13 интеграционных тестов
│   ├── test_integration_nodes.py     # 20 интеграционных тестов
│   └── test_integration_incidents.py # 20 интеграционных тестов
├── requirements.txt
├── pytest.ini
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## Быстрый старт (без Docker)

### 1. Установить зависимости

```bash
pip install -r requirements.txt
```

### 2. Запустить приложение

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Приложение запустится на http://localhost:8000  
Автоматически создаст БД и заполнит тестовыми данными.

### 3. Открыть документацию API

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

---

## Быстрый старт (с Docker)

```bash
docker-compose up --build
```

---

## Запуск тестов (ЛР3)

```bash
# Все тесты (66 штук)
python -m pytest tests/ -v

# Только модульные
python -m pytest tests/test_unit_security.py -v

# Только интеграционные
python -m pytest tests/test_integration_auth.py -v
python -m pytest tests/test_integration_nodes.py -v
python -m pytest tests/test_integration_incidents.py -v

# С отчётом о покрытии (нужен pip install pytest-cov)
python -m pytest tests/ --cov=app --cov-report=term-missing
```

Ожидаемый результат: **66 passed**

---

## Тестовые учётные данные (seed)

| Пользователь | Пароль   | Роль   | Права                                |
|-------------|----------|--------|--------------------------------------|
| admin       | admin123 | admin  | Полный доступ: CRUD + удаление        |
| sre_ivanov  | sre123   | sre    | Создание/обновление узлов, инцидентов |
| viewer_guest| view123  | viewer | Только чтение                         |

---

## API эндпоинты

### Аутентификация
```
POST   /api/v1/auth/token         - Вход, получение JWT
POST   /api/v1/auth/register      - Регистрация (только admin)
GET    /api/v1/auth/me            - Текущий пользователь
GET    /api/v1/auth/users         - Список пользователей (только admin)
```

### Узлы (Nodes)
```
GET    /api/v1/nodes/             - Список (все авторизованные)
GET    /api/v1/nodes/{id}         - Получить по ID
POST   /api/v1/nodes/             - Создать (admin, sre)
PATCH  /api/v1/nodes/{id}         - Обновить (admin, sre)
DELETE /api/v1/nodes/{id}         - Удалить (только admin)
GET    /api/v1/nodes/stats/summary - Статистика online/offline
```

### Инциденты (Incidents)
```
GET    /api/v1/incidents/                    - Список
GET    /api/v1/incidents/{id}                - По ID
POST   /api/v1/incidents/                    - Создать (admin, sre)
PATCH  /api/v1/incidents/{id}                - Обновить (admin, sre)
DELETE /api/v1/incidents/{id}                - Удалить (только admin)
POST   /api/v1/incidents/webhook/alertmanager - Webhook от Prometheus
GET    /api/v1/incidents/stats/summary        - Статистика
```

### Наблюдаемость (ЛР3)
```
GET    /api/v1/health    - Статус приложения
GET    /api/v1/metrics   - Метрики: RPS, latency, top endpoints
```

---

## Пример использования (curl)

```bash
# Шаг 1: Получить токен
TOKEN=$(curl -s -X POST "http://localhost:8000/api/v1/auth/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin123" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Шаг 2: Создать узел
curl -X POST "http://localhost:8000/api/v1/nodes/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"hostname":"prod-new-01","ip_address":"10.0.5.1","os_type":"linux","location":"DC-1"}'

# Шаг 3: Создать инцидент
curl -X POST "http://localhost:8000/api/v1/incidents/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"CPU spike","severity":"critical","node_id":1}'

# Шаг 4: Обновить статус инцидента
curl -X PATCH "http://localhost:8000/api/v1/incidents/1" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status":"resolved"}'

# Шаг 5: Метрики
curl "http://localhost:8000/api/v1/metrics" \
  -H "Authorization: Bearer $TOKEN"
```

---

