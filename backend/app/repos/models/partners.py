"""Организации-партнёры проекта.

Связь, а не список в поле проекта: у одного проекта партнёров несколько, и у каждого своя
роль. Хранить их строкой означало бы потерять ответ на вопрос «с какими организациями мы
работаем» — тот самый, ради которого справочник организаций и заводился (ТЗ 6.1,
сценарий U6).
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.repos.base import Base, Timestamps, UUIDPrimaryKey
from app.repos.models.audit import Auditable


class ProjectPartner(Auditable, UUIDPrimaryKey, Timestamps, Base):
    """Организация, участвующая в проекте, и её роль."""

    __tablename__ = "project_partners"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # Организация остаётся в справочнике, даже когда проект закрыт: удаление партнёра из
    # справочника не должно стирать историю, с кем мы работали. Поэтому не CASCADE, а
    # запрет удаления, пока связь существует.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )

    # Роль текстом, как в SPEC 1.3: «исполнитель», «заказчик», «соисполнитель». Если по
    # ролям понадобится считать, она станет справочником — свободный ввод к тому времени
    # даст три написания одного слова. Пока по ним не считают, справочник был бы вводом
    # ради формы.
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        # Одна организация участвует в проекте один раз. Две записи об одном партнёре —
        # это не «две роли», а ошибка ввода: роль пишется в одной строке.
        #
        # Имя не задаётся: для `uq` соглашение из `repos.base` строит его по столбцам, и
        # переданное имя его вытесняет целиком — ограничение оказалось бы единственным в
        # схеме, названным не по правилу, а откат миграции искал бы его по чужому имени.
        UniqueConstraint("project_id", "organization_id"),
        # «С какими организациями идёт этот проект» и «в каких проектах эта организация» —
        # два вопроса, и второй задаётся из карточки организации (готовится к ORB-033).
        Index("ix_project_partners_organization_id", "organization_id"),
    )
