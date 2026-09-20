"""Основание модели данных.

Здесь два решения, которые дороже всего менять потом.

**Схема `orbita` задаётся подключением, а не моделью.** Таблицы живут в ней, а не в
`public`: база делится с ассистентом SETA
([ADR-0001](../../../docs/adr/ADR-0001-architecture-variant.md)), и без своей схемы
имена рано или поздно столкнутся. Но имя схемы в `MetaData` не прописано намеренно:
тогда отражение базы и модели дают разное представление одного и того же внешнего
ключа, и `alembic check` бесконечно предлагает его пересоздать. Схему проставляет
`search_path` — единообразно и для приложения, и для миграций.

**Соглашение об именовании ограничений.** PostgreSQL сам придумывает имена индексам и
ограничениям, а Alembic по этим именам их потом удаляет. Имена, придуманные базой, у
разных установок разные — и откат миграции падает там, где его никто не проверял. Правила
ниже делают имена одинаковыми везде.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from typing import Any

from sqlalchemy import DateTime, Integer, MetaData, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

SCHEMA = "orbita"

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)


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
    бота (CLAUDE.md, инвариант о времени).

    `DateTime(timezone=True)` указывается явно: по одной аннотации `Mapped[datetime]`
    SQLAlchemy выводит `timestamp without time zone`. Разница не видна ни в модели, ни
    на ревью — она обнаруживается, когда руководитель в поездке видит сдвинутые сроки.
    Схема целиком проверяется тестом `test_no_naive_timestamp_columns`.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        onupdate=func.now(),
        nullable=True,
    )


class Versioned:
    """Версия записи: защита от молчаливой перезаписи (инвариант 15).

    Пользователей двое, и они правят одно и то же чаще, чем кажется: помощник вносит
    перенос срока ровно тогда, когда руководитель смотрит на этот проект с телефона. Без
    версии тот, кто сохранил вторым, затирает первого — и никто из них об этом не
    узнаёт.

    Считает версию сама SQLAlchemy: при сохранении она добавляет в условие `WHERE`
    прежнее значение и, если строку уже изменили, поднимает `StaleDataError`. Сервисный
    слой превращает его в честный ответ «запись изменил помощник» с кнопкой «обновить»
    ([ADR-0034](../../../docs/adr/ADR-0034-near-real-time.md)).

    **Следствие, о котором легко забыть:** запись, изменённая запросом `UPDATE` мимо
    ORM, версию не поднимает. Поэтому деловые записи правятся только через объекты, а
    `update()` остаётся для служебных таблиц вроде сессий, у которых версии нет.
    """

    version: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"), default=1
    )

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:  # noqa: N805
        return {"version_id_col": cls.version}
