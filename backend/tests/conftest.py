"""Shared pytest configuration for backend tests.

Provides a ``db_engine`` fixture that creates a SQLAlchemy engine backed by
PostgreSQL (when ``TEST_DATABASE_URL`` is set) or falls back to an in-memory
SQLite database for local development without a running PostgreSQL instance.

Usage in test files::

    @pytest.fixture()
    def client(db_engine):
        SessionLocal = sessionmaker(bind=db_engine, ...)
        Base.metadata.create_all(bind=db_engine)
        ...
"""

from __future__ import annotations

import os
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Determine the test database URL from the environment.
# ---------------------------------------------------------------------------
TEST_DATABASE_URL: str = os.environ.get("TEST_DATABASE_URL", "")
_USE_POSTGRES: bool = TEST_DATABASE_URL.startswith("postgresql")

if _USE_POSTGRES:
    print(f"\n[conftest] Using PostgreSQL test database: {TEST_DATABASE_URL}", file=sys.stderr)
else:
    print("\n[conftest] Using SQLite in-memory test database (set TEST_DATABASE_URL for PostgreSQL)", file=sys.stderr)


# ---------------------------------------------------------------------------
# Database name used exclusively by the Python test-suite so that it never
# collides with the Rust integration-test database on the same PostgreSQL
# service container.
# ---------------------------------------------------------------------------
_PYTHON_TEST_DB = "eln_test_py"


def sqlalchemy_postgres_url(url: str) -> str:
    """Use the psycopg v3 driver declared by requirements-base.txt."""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    return url


@pytest.fixture()
def db_engine():
    """Yield a SQLAlchemy engine for the test session.

    * PostgreSQL: creates a dedicated database, enables the ``vector``
      extension, yields the engine, then drops the database.
    * SQLite: returns an in-memory engine with ``StaticPool``.

    Tables are created by each test fixture (``Base.metadata.create_all``)
    and dropped in the teardown phase of this fixture.
    """
    if _USE_POSTGRES:
        # -- Connect to the default database to create / drop the test DB ----
        default_url = sqlalchemy_postgres_url(TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres")
        admin_engine = create_engine(default_url, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as conn:
            # Terminate existing sessions so DROP DATABASE succeeds.
            conn.execute(text(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE datname = :db AND pid <> pg_backend_pid()"
            ), {"db": _PYTHON_TEST_DB})
            conn.execute(text(f'DROP DATABASE IF EXISTS "{_PYTHON_TEST_DB}"'))
            conn.execute(text(f'CREATE DATABASE "{_PYTHON_TEST_DB}"'))
        admin_engine.dispose()

        # -- Connect to the freshly created test database --------------------
        test_url = sqlalchemy_postgres_url(
            TEST_DATABASE_URL.rsplit("/", 1)[0] + f"/{_PYTHON_TEST_DB}"
        )
        engine = create_engine(
            test_url,
            pool_pre_ping=True,
        )
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
    else:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

    yield engine

    # -- Teardown ------------------------------------------------------------
    if _USE_POSTGRES:
        # Close all pooled connections before dropping the database.
        engine.dispose()
        admin_engine = create_engine(default_url, isolation_level="AUTOCOMMIT")
        with admin_engine.connect() as conn:
            conn.execute(text(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE datname = :db AND pid <> pg_backend_pid()"
            ), {"db": _PYTHON_TEST_DB})
            conn.execute(text(f'DROP DATABASE IF EXISTS "{_PYTHON_TEST_DB}"'))
        admin_engine.dispose()
    else:
        engine.dispose()
