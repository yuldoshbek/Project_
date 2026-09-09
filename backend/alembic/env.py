"""Окружение Alembic.

Три вещи здесь важнее остального.

1. **Строка подключения берётся из настроек**, а не из `alembic.ini`: репозиторий
   публичный, паролю в файле не место.
2. **Служебная таблица `alembic_version` живёт в схеме `orbita`.** По умолчанию она
   создаётся в `public` — а `public` мы делим с SETA
   ([ADR-0001](../../docs/adr/ADR-0001-architecture-variant.md)), и две системы начали бы
   переписывать номер версии друг другу.
3. **Автогенерация видит только схему `orbita`.** Без ограничения Alembic предложит
   удалить всё, что найдёт в чужих схемах, — и однажды кто-нибудь применит такую миграцию.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.repos.base import SCHEMA, Base
from app.settings import get_settings

# Импорт нужен ради побочного эффекта: автогенерация видит только те таблицы, чей
# модуль загружен. Забытый импорт означает миграцию, молча удаляющую таблицу.
import app.repos.models  # noqa: F401  isort:skip

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    """Адрес базы: переданный вызывающим либо из настроек.

    Переопределение нужно тестам — они прогоняют миграции на отдельной базе, чтобы
    `downgrade base` не сносил ничего нужного.
    """
    override = config.attributes.get("db_url")
    if isinstance(override, str):
        return override
    return get_settings().database_url


def include_object(
    _object: Any,
    _name: str | None,
    type_: str,
    _reflected: bool,
    compare_to: Any,
) -> bool:
    """Оставляет автогенерации только объекты схемы `orbita`."""
    if type_ == "table":
        schema = getattr(_object, "schema", None) or getattr(compare_to, "schema", None)
        return schema == SCHEMA
    return True


def configure(connection: Connection | None = None, url: str | None = None) -> None:
    options: dict[str, Any] = {
        "target_metadata": target_metadata,
        "version_table_schema": SCHEMA,
        "include_schemas": True,
        "include_object": include_object,
        # Изменение типа столбца иначе останется незамеченным: Alembic по умолчанию
        # сравнивает только состав столбцов, но не их тип и значение по умолчанию.
        "compare_type": True,
        "compare_server_default": True,
    }
    if connection is not None:
        context.configure(connection=connection, **options)
    else:
        context.configure(
            url=url,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            **options,
        )


def run_migrations_offline() -> None:
    """Печать SQL без подключения — для согласования изменений с администратором базы."""
    configure(url=database_url())
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    configure(connection=connection)
    with context.begin_transaction():
        # Схема должна существовать до того, как Alembic создаст в ней свою таблицу версий.
        connection.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')
        context.run_migrations()


async def run_migrations_online() -> None:
    section: dict[str, Any] = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = database_url()

    engine = async_engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


def main(_: Iterable[str] | None = None) -> None:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        asyncio.run(run_migrations_online())


main()
