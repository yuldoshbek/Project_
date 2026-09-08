"""Основание модели данных.

Здесь два решения, которые дороже всего менять потом.

**Схема `orbita`.** Все таблицы живут в ней, а не в `public`: база делится с ассистентом
SETA ([ADR-0001](../../../docs/adr/ADR-0001-architecture-variant.md)), и без своей схемы
имена рано или поздно столкнутся.

**Соглашение об именовании ограничений.** PostgreSQL сам придумывает имена индексам и
ограничениям, а Alembic по этим именам их потом удаляет. Имена, придуманные базой, у
разных установок разные — и откат миграции падает там, где его никто не проверял. Правила
ниже делают имена одинаковыми везде.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "orbita"

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(schema=SCHEMA, naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Базовый класс моделей."""

    metadata = metadata


class UUIDPrimaryKey:
    """Первичный ключ типа UUID.

    Значение выдаёт база (`gen_random_uuid` из pgcrypto), а не приложение: так
    идентификатор существует и у записей, созданных миграцией данных или вручную.
    Последовательные целые не годятся — по ним перебором узнаётся объём портфеля.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )


class Timestamps:
    """Отметки создания и изменения.

    `timestamptz` и `now()` на стороне базы — время одно на всех: у приложения, воркера и
    бота (CLAUDE.md, инвариант о времени). Наивных дат в схеме нет и быть не может.
    """

    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        onupdate=func.now(),
        nullable=True,
    )
