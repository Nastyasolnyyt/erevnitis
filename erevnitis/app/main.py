import os
import asyncio  # Обязательный импорт для фоновых задач
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.core.database import engine, Base
from app.core.observability import LoggingMetricsMiddleware, metrics, logger
from app.modules.auth.router      import router as auth_router
from app.modules.nodes.router     import router as nodes_router
from app.modules.incidents.router import router as incidents_router
from app.modules.metrics.router   import router as metrics_router
from app.modules.audit.router     import router as audit_router
from app.modules.analytics.router import router as analytics_router

# Импортируем наш мост для Прометея
from app.core.prometheus_bridge import prometheus_sync_loop

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
templates  = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# 1. Определяем lifespan (жизненный цикл приложения)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Импортируем модели до создания таблиц (чтобы SQLAlchemy их увидела)
    from app.modules.auth.models     import User
    from app.modules.nodes.models    import Node
    from app.modules.incidents.models import Incident
    from app.modules.metrics.models  import MetricHistory
    from app.modules.audit.models    import AuditLog
    
    Base.metadata.create_all(bind=engine)
    
    # Сидирование БД тестовыми данными
    from app.core.seed import seed_database
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
        
    logger.info("Erevnitis SRE Panel v3 запущен.")
    
    # ЗАПУСК ФОНОВОГО МОСТА PROMETHEUS
    # Эта таска будет крутиться в фоне всё время, пока работает FastAPI
    bridge_task = asyncio.create_task(prometheus_sync_loop(interval_seconds=15))
    
    yield  # Здесь приложение работает и обрабатывает запросы
    
    # При выключении приложения аккуратно завершаем фоновую таску
    bridge_task.cancel()
    try:
        await bridge_task
    except asyncio.CancelledError:
        pass
    logger.info("Erevnitis SRE Panel остановлен.")

# 2. Инициализируем FastAPI строго ОДИН раз, передавая lifespan
app = FastAPI(title="Erevnitis SRE Panel API", version="3.0.0", lifespan=lifespan)

# Настройка Middlewares
app.add_middleware(LoggingMetricsMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

# Монтирование статики
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Подключение API роутеров
app.include_router(auth_router,      prefix="/api/v1/auth",      tags=["Auth"])
app.include_router(nodes_router,     prefix="/api/v1/nodes",     tags=["Nodes"])
app.include_router(incidents_router, prefix="/api/v1/incidents", tags=["Incidents"])
app.include_router(metrics_router,   prefix="/api/v1/metrics",   tags=["Metrics"])
app.include_router(audit_router,     prefix="/api/v1/audit",     tags=["Audit"])
app.include_router(analytics_router, prefix="/api/v1/analytics", tags=["Analytics"])

# Системные эндпоинты
@app.get("/api/v1/health")
def health():
    return {"status": "healthy", "version": "3.0.0"}

@app.get("/api/v1/system-metrics")
def system_metrics():
    return metrics.get_summary()

# ---------------------------------------------------------
# Web UI Роуты (HTML страницы)
# ---------------------------------------------------------

# Оставил только один рут для "/", который показывает Landing.
# Если хочешь, чтобы при заходе на корень кидало сразу в панель, 
# замени return templates... на return RedirectResponse(url="/dashboard")
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/nodes", response_class=HTMLResponse)
async def nodes_page(request: Request):
    return templates.TemplateResponse("nodes.html", {"request": request})

@app.get("/nodes/{node_id}", response_class=HTMLResponse)
async def node_detail(request: Request, node_id: int):
    return templates.TemplateResponse("node_detail.html",
                                      {"request": request, "node_id": node_id})

@app.get("/incidents", response_class=HTMLResponse)
async def incidents_page(request: Request):
    return templates.TemplateResponse("incidents.html", {"request": request})

@app.get("/sla", response_class=HTMLResponse)
async def sla_page(request: Request):
    return templates.TemplateResponse("sla.html", {"request": request})

@app.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request):
    return templates.TemplateResponse("audit.html", {"request": request})

@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    return templates.TemplateResponse("users.html", {"request": request})