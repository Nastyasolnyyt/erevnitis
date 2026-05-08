"""
Database configuration - SINGLE RESPONSIBILITY: only DB connection management
Follows DRY: one place for DB setup, reused via get_db dependency
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# SQLite for demo (swap to PostgreSQL in production: postgresql://user:pass@host/db)
DATABASE_URL = "sqlite:///./erevnitis.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}  # SQLite specific
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# DRY: single reusable DB session dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
