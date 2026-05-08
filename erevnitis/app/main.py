"""
Erevnitis SRE Panel - Main Application
Лабораторные работы №2 и №3
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.database import engine, Base
from app.core.observability import LoggingMetricsMiddleware, metrics, logger
from app.modules.auth.router import router as auth_router
from app.modules.nodes.router import router as nodes_router
from app.modules.incidents.router import router as incidents_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    from app.core.seed import seed_database
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
    logger.info("Erevnitis SRE Panel запущен. БД инициализирована.")
    yield
    logger.info("Erevnitis SRE Panel останавливается.")


app = FastAPI(
    title="Erevnitis SRE Panel API",
    description="Система управления инфраструктурой и инцидентами для SRE-команд",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(LoggingMetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(nodes_router, prefix="/api/v1/nodes", tags=["Nodes"])
app.include_router(incidents_router, prefix="/api/v1/incidents", tags=["Incidents"])


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "service": "Erevnitis SRE Panel", "version": "2.0.0"}


@app.get("/api/v1/health", tags=["Health"])
def health_check():
    return {"status": "healthy", "modules": ["auth", "nodes", "incidents"]}


@app.get("/api/v1/metrics", tags=["Observability"])
def get_metrics():
    """Метрики производительности: uptime, RPS, время ответа, топ эндпоинтов"""
    return metrics.get_summary()
