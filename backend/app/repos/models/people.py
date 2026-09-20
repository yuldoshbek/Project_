"""Люди: сотрудники и пользователи — два разных понятия (`app.domain.people`)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.repos.base import Base, Timestamps, UUIDPrimaryKey, Versioned
from app.repos.models.audit import Auditable


class Person(Auditable, Versioned, UUIDPrimaryKey, Timestamps, Base):
    """Сотрудник агентства или Центра. В систему не входит.

    Существует, чтобы было понятно, с кого спрашивать: ответственный за проект, задачу,
    поручение, запрос сведений. Журналируется: смена должности или подразделения — деловое
    изменение, и вопрос «кто это поменял» по ней возникает так же, как по проекту.

    Почта и телефон — способ связи, а не учётные данные: входа по ним нет и не будет
    ([ADR-0029](../../../docs/adr/ADR-0029-access-by-link.md)), поэтому они необязательны
    и не уникальны.
    """

    __tablename__ = "people"

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[str | None] = mapped_column(String(200), nullable=True)
    department: Mapped[str | None] = mapped_column(String(200), nullable=True)

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    """Агентство или Центр (ТЗ 3.8).

    Пусто означает агентство: заводить запись «Ўзбеккосмос» ради того, чтобы проставить
    её каждому из десятков сотрудников, — это ввод, который ничего не сообщает.
    """

    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (Index("ix_people_full_name", "full_name"),)


class User(UUIDPrimaryKey, Timestamps, Base):
    """Пользователь системы. Их ровно двое: помощник и руководитель (ТЗ 3.8).

    Роль уникальна: третьего пользователя нет, и его появление — пересмотр решения о
    доступе целиком, а не строка в таблице (вопрос V9 в открытых).

    Ни адреса почты, ни пароля здесь нет: вход — это личная ссылка, и опознаёт человека
    она. Часового пояса тоже нет: он один на всю систему, `Asia/Tashkent` (инвариант 8);
    хранить его у пользователя значило бы разрешить двум людям видеть разные сроки у
    одного поручения.

    Версии у записи нет намеренно: её не правят двое — её вообще почти не правят.
    """

    __tablename__ = "users"

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)

    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="SET NULL"), nullable=True
    )
    """Помощник и руководитель — тоже сотрудники агентства. Связь необязательная и
    односторонняя: у сотрудника ссылки на пользователя нет."""

    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="ru")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    last_visit_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """Когда пользователь смотрел систему в прошлый раз.

    Отсюда берётся «С прошлого визита» (ТЗ 4) — строка, ради которой руководитель и
    открывает Пульт после поездки. Отметка сдвигается при входе, а не при каждом запросе:
    иначе «прошлый визит» всегда оказывался бы пятнадцатью секундами назад.
    """
