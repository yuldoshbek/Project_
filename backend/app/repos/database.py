"""Подключение к базе данных.

Единственное место, где создаётся движок и сессия. Транзакция живёт на время запроса:
успешный ответ фиксируется, исключение откатывает всё, включая запись в журнал изменений
(ADR-0010) — иначе в журнале останется след от изменения, которого не произошло.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.settings import Settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.sqlalchemy_url,
        echo=False,
        # Соединение из пула могло быть закрыто площадкой, пока функция спала. Без этой
        # проверки первый запрос после простоя отвечает ошибкой, а не данными.
        pool_pre_ping=True,
        # Схема поиска, TLS и отключение кеша подготовленных запросов за пулом —
        # всё это собирает settings.connect_args, чтобы правило жило в одном месте.
        connect_args=settings.connect_args,
    )


def init_database(settings: Settings) -> None:
    global _engine, _session_factory
    _engine = create_engine(settings)
    _session_factory = async_sessionmaker(
        _engine,
        expire_on_commit=False,
        autoflush=False,
    )


async def dispose_database() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("движок не создан: вызовите init_database при запуске приложения")
    return _engine


def new_session() -> AsyncSession:
    """Сессия из фабрики. Закрывать и фиксировать — забота вызывающего."""
    if _session_factory is None:
        raise RuntimeError("фабрика сессий не создана: вызовите init_database")
    return _session_factory()


async def session_scope() -> AsyncIterator[AsyncSession]:
    """Сессия на время работы: фиксация при успехе, откат при исключении.

    Для фоновых заданий, сидов и командной строки — там граница транзакции совпадает с
    границей работы, и фиксировать в конце правильно.

    **Обработчики HTTP-запросов пользуются не этим**, а `api.deps.get_session`: там
    фиксация обязана случиться до отправки ответа, а разбор зависимости происходит после
    (`api.transaction`).
    """
    async with new_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()
