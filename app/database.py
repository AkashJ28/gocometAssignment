"""Database engine, connection pooling, and session management for trade documents."""

import os
from contextlib import contextmanager
from typing import Generator, Optional
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session
from app.models import Base

DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/trade_docs"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def create_db_engine(db_url: Optional[str] = None) -> Engine:
    """Create a configured SQLAlchemy engine supporting SQLite and PostgreSQL."""
    target_url = db_url or DATABASE_URL
    if target_url.startswith("sqlite"):
        return create_engine(
            target_url,
            connect_args={"check_same_thread": False},
        )
    return create_engine(
        target_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )


engine: Engine = create_db_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db(engine_override: Optional[Engine] = None) -> None:
    """Initialize all schema tables."""
    target_engine = engine_override or engine
    Base.metadata.create_all(bind=target_engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for obtaining a transactional database session."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_db_session(session_factory: Optional[sessionmaker] = None) -> Generator[Session, None, None]:
    """Context manager for obtaining a database session."""
    factory = session_factory or SessionLocal
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
