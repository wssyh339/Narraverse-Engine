from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
database_url = settings.database_url

if database_url.startswith("sqlite"):
    url = make_url(database_url)
    database = url.database
    if database and database not in {":memory:"}:
        Path(database).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    database_url,
    echo=settings.sql_echo,
    connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
