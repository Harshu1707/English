from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


# MySQL database engine
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
)


# Database session
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


# Base class for SQLAlchemy models
class Base(DeclarativeBase):
    pass


# Dependency for FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

