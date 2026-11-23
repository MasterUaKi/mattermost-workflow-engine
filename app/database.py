# Автор: Oleh Riabtsev
# Файл: app/database.py
# Дата создания: 2026-11-23
# Версия: 1.0.0

"""
Модуль инициализации асинхронного подключения к базе данных (SQLite / PostgreSQL)
на базе SQLAlchemy 2.0.
"""

from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

# Создаем асинхронный движок SQLAlchemy 2.0
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
)

# Фабрика асинхронных сессий
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Базовый класс для всех декларативных моделей SQLAlchemy 2.0."""
    pass


async def init_db() -> None:
    """Создает таблицы в базе данных при старте MVP-приложения."""
    from app import models  # noqa: F401 — импорт для регистрации метаданных моделей

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Зависимость FastAPI (Dependency Injection) для предоставления сессии БД на запрос."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
