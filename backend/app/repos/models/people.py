"""Пользователи системы и сотрудники агентства.

Две разные таблицы для двух разных понятий — обоснование в `app.domain.people`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.repos.base import Base, Timestamps, UUIDPrimaryKey


class Person(UUIDPrimaryKey, Timestamps, Base):
    """Сотрудник агентства.

    В систему не входит. Существует, чтобы было понятно, с кого спрашивать: куратор
    проекта, исполнитель задачи, участник встречи.

    Почта необязательна и не уникальна как учётные данные: это способ связи, а не логин.
    Уникален только адрес пользователя (`users.email`), потому что по нему входят.
    """

    __tablename__ = "people"

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[str | None] = mapped_column(String(200), nullable=True)
    department: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(CITEXT, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        # Поиск по ФИО — основной способ выбрать куратора в форме создания (ТЗ 10.5:
        # не более трёх шагов). Полноценный поиск на трёх письменностях — ORB-033.
        Index("ix_people_full_name", "full_name"),
    )


class User(UUIDPrimaryKey, Timestamps, Base):
    """Пользователь системы. Их двое (ADR-0011).

    `external_seta_id` заведён с первой миграции, хотя SETA ещё в разработке: добавить
    столбец в заполненную таблицу дороже, чем оставить его пустым
    ([ADR-0001](../../../docs/adr/ADR-0001-architecture-variant.md)).
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)

    role: Mapped[str] = mapped_column(String(20), nullable=False)
    """Роль из `app.domain.people.Role`.

    Хранится строкой, а не типом-перечислением PostgreSQL: добавить значение в
    перечисление базы можно только миграцией с блокировкой таблицы, а строка проверяется
    на входе в приложении. При двух ролях выигрыш типа не окупает эту жёсткость.
    """

    person_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("people.id", ondelete="SET NULL"),
        nullable=True,
    )
    """Тот же человек в справочнике сотрудников.

    Помощник и руководитель — тоже сотрудники агентства: на них записывают проекты.
    Связь необязательная, чтобы завести пользователя можно было и без карточки сотрудника.
    """

    person: Mapped[Person | None] = relationship(lazy="joined")

    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    """Пусто, когда вход идёт через внешнего провайдера (ADR-0001)."""

    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    """Пароль выдан администратором и должен быть заменён при первом входе."""

    telegram_id: Mapped[int | None] = mapped_column(nullable=True, unique=True)
    """Получатель сообщений бота. Белый список — это буквально непустые значения
    этого столбца ([ADR-0013](../../../docs/adr/ADR-0013-telegram-bot.md))."""

    external_seta_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)

    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="ru")
    timezone: Mapped[str] = mapped_column(String(50), nullable=False, default="Asia/Tashkent")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    failed_login_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    """Счётчик и блокировка живут в записи пользователя, а не в памяти процесса.

    В памяти они обнулялись бы при каждом перезапуске и при работе второго процесса
    (воркер, бот) не учитывались бы вовсе — то есть ограничение частоты попыток входа
    существовало бы только на бумаге.
    """
