from pathlib import Path

from sqlalchemy import create_engine, event
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

is_sqlite = database_url.startswith("sqlite")

engine = create_engine(
    database_url,
    echo=settings.sql_echo,
    connect_args={"check_same_thread": False, "timeout": 30} if is_sqlite else {},
)


if is_sqlite:

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        if database_url != "sqlite:///:memory:":
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
