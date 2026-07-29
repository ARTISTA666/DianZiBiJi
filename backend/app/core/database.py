from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
_connect_args: dict = {}
_pool_kwargs: dict = {}

if _settings.database_url.startswith("sqlite"):
    _connect_args["check_same_thread"] = False
else:
    _pool_kwargs = {
        "pool_size": _settings.db_pool_size,
        "max_overflow": _settings.db_max_overflow,
        "pool_recycle": _settings.db_pool_recycle,
        "pool_timeout": _settings.db_pool_timeout,
    }

engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    connect_args=_connect_args,
    **_pool_kwargs,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
