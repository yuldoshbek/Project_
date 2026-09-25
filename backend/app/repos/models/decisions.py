"""Вопросы к руководителю и журнал его решений (ТЗ 3.7, ТЗ 4).

Решения — единственная таблица, в которую пишет руководитель. Ради неё и существует Пульт:
строка лестницы внимания заканчивается кнопкой, кнопка заводит здесь запись, и по ней
потом видно, что из решённого выполнено. Вопрос — то, что ставит строку на верхнюю
ступень «ждёт решения»; ответом на него служит решение.

Ссылка на объект полиморфная — `target_type` плюс `target_id`. Внешним ключом её не
закрыть: решение принимают по проекту, задаче, вехе и поручению, а база такую связь не
выразит. Плата названа вслух: целостность держит сервисный слой, который уносит решения
вместе с объектом, и тест это стережёт.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy import text as sql  # у вопроса есть столбец `text`, он перекрыл бы функцию
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.decisions import DecisionKind, DecisionState, DecisionTarget
from app.repos.base import Base, Timestamps, UUIDPrimaryKey, Versioned
from app.repos.models.audit import Auditable

KINDS = ", ".join(f"'{kind.value}'" for kind in DecisionKind)
STATES = ", ".join(f"'{state.value}'" for state in DecisionState)
TARGETS = ", ".join(f"'{target.value}'" for target in DecisionTarget)


class LeaderDecision(Auditable, Versioned, UUIDPrimaryKey, Timestamps, Base):
    """Действие руководителя по объекту, с ответственным и сроком исполнения."""

    __tablename__ = "leader_decisions"

    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Пояснение к решению. Необязательно: «утвердить» в одно касание — это решение
    целиком, и требовать к нему текст значит сделать одно касание двумя экранами."""

    assignee_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="SET NULL"), nullable=True
    )
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    state: Mapped[str] = mapped_column(String(20), nullable=False, default=DecisionState.OPEN.value)
    """Открыто или выполнено. «Просрочено» вычисляется (`app.domain.decisions`)."""

    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    done_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        CheckConstraint(f"target_type IN ({TARGETS})", name="target_type_is_known"),
        CheckConstraint(f"kind IN ({KINDS})", name="kind_is_known"),
        CheckConstraint(f"state IN ({STATES})", name="state_is_known"),
        CheckConstraint(
            "(state = 'done' AND done_on IS NOT NULL) OR (state = 'open' AND done_on IS NULL)",
            name="done_decision_has_a_date",
        ),
        # «Что ждёт моего решения» и «что я решил, но не сделано» — два самых частых
        # вопроса Пульта, и оба читаются этим индексом.
        Index("ix_leader_decisions_state_due_on", "state", "due_on"),
        Index("ix_leader_decisions_target_type_target_id", "target_type", "target_id"),
    )


class LeaderQuestion(Auditable, Versioned, UUIDPrimaryKey, Timestamps, Base):
    """Открытый вопрос к руководителю по объекту — ступень «ждёт решения» (ТЗ 4).

    Ставит помощник, когда без руководителя дальше нельзя. Закрывается ответом —
    решением руководителя (`decision_id`) — или снимается помощником, если вопрос отпал
    (`closed_at` без решения). Дата постановки — это `created_at`: от неё считается
    «старейшее ожидание» Пульта (ТЗ 5).

    Отдельная таблица, а не поле у проекта, задачи, вехи и поручения: одно правило вместо
    четырёх копий, и ответ связан с вопросом ссылкой, а не догадкой по времени.
    """

    __tablename__ = "leader_questions"

    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    """Что именно нужно решить. Обязательно: строка «ждёт решения» без вопроса оставляет
    руководителю угадывать, о чём его спрашивают."""

    asked_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leader_decisions.id", ondelete="SET NULL"), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(f"target_type IN ({TARGETS})", name="target_type_is_known"),
        # Ответ без закрытия — вопрос, который числится открытым, хотя на него ответили:
        # он висел бы на верхней ступени вечно.
        CheckConstraint(
            "decision_id IS NULL OR closed_at IS NOT NULL", name="answered_question_is_closed"
        ),
        # Лестница спрашивает только открытые вопросы, и только по объекту.
        Index(
            "ix_leader_questions_open_target",
            "target_type",
            "target_id",
            postgresql_where=sql("closed_at IS NULL"),
        ),
    )
