from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.config import DATABASE_URL

# Use synchronous driver (psycopg2) for this app; if URL uses asyncpg, switch to psycopg2.
_url = DATABASE_URL
if "asyncpg" in _url:
    _url = _url.replace("postgresql+asyncpg", "postgresql+psycopg2", 1)

engine = create_engine(_url, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

