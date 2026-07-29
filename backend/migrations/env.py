from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.core.database import Base
from app.models import *  # noqa: F403


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

configured_url = config.get_main_option("sqlalchemy.url")
database_url = os.getenv("DATABASE_URL")
if not database_url and configured_url and not configured_url.startswith("driver://"):
    database_url = configured_url
database_url = database_url or get_settings().database_url
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata
PRESERVED_LEGACY_TABLES = {"group_projects"}


def include_object(obj, name: str | None, type_: str, reflected: bool, compare_to) -> bool:
    return not (
        type_ == "table"
        and reflected
        and compare_to is None
        and name in PRESERVED_LEGACY_TABLES
    )


def compare_type(_context, inspected_column, metadata_column, _inspected_type, _metadata_type):
    if (
        inspected_column.table.name == "rag_document_chunks"
        and metadata_column.name == "embedding"
    ):
        return False
    return None


def configure(connection=None, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        compare_type=compare_type,
        include_object=include_object,
        render_as_batch=connection is not None and connection.dialect.name == "sqlite",
        literal_binds=url is not None,
        dialect_opts={"paramstyle": "named"} if url is not None else None,
    )


def run_migrations_offline() -> None:
    configure(url=config.get_main_option("sqlalchemy.url"))
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
