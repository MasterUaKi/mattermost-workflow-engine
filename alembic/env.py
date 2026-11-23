# Author: Oleh Riabtsev
# File: alembic/env.py
# Created: 2026-11-23
# Version: 1.0.0

"""
Asynchronous Alembic environment configuration for SQLAlchemy 2.0 and PostgreSQL (asyncpg).
Dynamically resolves DATABASE_URL from application settings and registers all ORM models
for autogenerate support.
"""

import asyncio
from logging.config import fileConfig
from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import get_settings
from app.database import Base
from app import models  # noqa: F401 — ensure all ORM models are registered on Base.metadata

# Alembic Config object providing access to values within alembic.ini
config = context.config

# Configure Python loggers from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target SQLAlchemy MetaData for 'autogenerate' migration support
target_metadata = Base.metadata


def get_database_url() -> str:
    """Loads DATABASE_URL from application settings and escapes '%' for configparser."""
    settings = get_settings()
    return settings.DATABASE_URL.replace("%", "%%")


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode without an active database connection.
    Emits SQL statements directly to the script output.
    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Executes migrations synchronously inside an async database connection context."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Creates an async SQLAlchemy engine and executes migrations online."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entrypoint for running migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
