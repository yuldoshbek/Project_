"""Проекты и программы (ТЗ 3.1).

Программа — это не отдельная таблица, а признак `is_multiyear` у проекта. Разница между
ними в горизонте и в том, где их показывают, а не в устройстве: у программы те же вехи,
тот же ответственный и тот же срок. Две таблицы означали бы два набора запросов, две
формы и два места, где считается готовность, — а вопрос «где мы по этой работе» у них
общий.

Ссылка на справочник статусов идёт по `code`, а не по идентификатору: код известен коду
(`app.domain.dictionaries`), и запрос «все приостановленные» читается без соединения с
таблицей статусов. Переименование статуса при этом ничего не ломает — меняется название,
не код.

**Готовности здесь нет.** Она считается по закрытым вехам и задачам (`app.domain.projects`,
`readiness`), а хранимое число разошлось бы с тем, из чего оно посчитано, и разошлось бы
молча — то же правило, что у просрочки (инвариант 1).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.repos.base import Base, Timestamps, UUIDPrimaryKey, Versioned
from app.repos.models.audit import Auditable


class Project(Auditable, Versioned, UUIDPrimaryKey, Timestamps, Base):
    """Работа агентства с целью, сроком, вехами и одним ответственным."""

    __tablename__ = "projects"

    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    project_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_types.id"), nullable=False
    )

    parent_project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=True
    )
    """Родительский проект. Одна ступень вложенности (`app.domain.projects`, NESTING_DEPTH).

    `RESTRICT`, а не `CASCADE`: удаление программы не должно молча уносить подпроекты,
    каждый из которых — самостоятельная работа с ответственным и сроком.
    """

    is_multiyear: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    """Признак программы: показывается в разделе «Программы» с горизонтом лет (ТЗ 2)."""

    started_on: Mapped[date] = mapped_column(Date, nullable=False)
    due_on: Mapped[date] = mapped_column(Date, nullable=False)

    original_due_on: Mapped[date] = mapped_column(Date, nullable=False)
    """Первое значение срока. Ведётся системой, не человеком (ТЗ 3.1).

    Без него вопрос «держим ли мы свои сроки» (ТЗ 5) не имеет ответа: перенос виден в
    журнале изменений, но собирать по журналу число переносов и суммарный сдвиг для
    двухсот проектов — это запрос, который никто не станет ждать.
    """

    status_code: Mapped[str] = mapped_column(
        String(50), ForeignKey("project_statuses.code"), nullable=False
    )
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    responsible_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="SET NULL"), nullable=True
    )
    """Ответственный: у объекта он ровно один (CONTEXT).

    Необязателен при заведении: обязательных полей у проекта два — название и тип
    (ТЗ 7), а ответственного помощник проставит, когда решит, с кого спрашивать.
    """

    direction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("directions.id"), nullable=True
    )
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("regions.id"), nullable=True
    )

    impediment: Mapped[str | None] = mapped_column(Text, nullable=True)
    impediment_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """Когда «что мешает» подтверждали в последний раз.

    Дата хранится рядом с текстом, потому что строка без даты выглядит одинаково свежей и
    месячной давности, а решение по ней принимают разное.
    """

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint("due_on >= started_on", name="due_on_is_not_before_started_on"),
        CheckConstraint(
            "status_code NOT IN ('on_hold', 'cancelled') "
            "OR (status_reason IS NOT NULL AND btrim(status_reason) <> '')",
            name="paused_and_cancelled_need_a_reason",
        ),
        CheckConstraint("parent_project_id <> id", name="project_is_not_its_own_parent"),
        # Лестница внимания читает проекты по сроку внутри незавершённых: это самый
        # частый запрос системы — с него начинается каждый показ Пульта.
        Index("ix_projects_status_code_due_on", "status_code", "due_on"),
        Index("ix_projects_parent_project_id", "parent_project_id"),
        Index("ix_projects_responsible_person_id_due_on", "responsible_person_id", "due_on"),
        # Раздел «Программы» выбирает многолетние по сроку — частичный индекс вместо
        # общего: программ единицы, а проектов сотни.
        Index(
            "ix_projects_multiyear_due_on",
            "due_on",
            postgresql_where="is_multiyear",
        ),
    )


class ProjectOrganization(Auditable, Versioned, UUIDPrimaryKey, Timestamps, Base):
    """Роль организации в проекте: заказчик, исполнитель, соисполнитель, головное ведомство.

    Связь, а не поле проекта: организаций у проекта несколько, и у каждой своя роль.
    Хранить их строкой означало бы потерять ответ на вопрос «что держит Центр» (ТЗ 5) —
    тот самый, ради которого учреждённая организация и отмечается признаком.

    Роль обязательна, в отличие от прежней схемы: связь без роли не отвечает ни на один
    вопрос — ни «кто заказчик», ни «из-за кого сорвётся».
    """

    __tablename__ = "project_organizations"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "role IN ('customer', 'executor', 'co_executor', 'lead_agency')",
            name="role_is_known",
        ),
        # Одна организация — одна роль в проекте. Вторая строка с другой ролью означала
        # бы, что ведомство одновременно заказчик и исполнитель, а на этом различии
        # держится сигнал «зависит от чужих».
        Index(
            "uq_project_organizations_project_id_organization_id",
            "project_id",
            "organization_id",
            unique=True,
        ),
        Index("ix_project_organizations_organization_id_role", "organization_id", "role"),
    )
