"""Прогоны задач по расписанию.

Таблица существует ради одного правила: **повторный запуск не делает работу дважды**
(CLAUDE.md, инвариант 10). Расписание доставляет вызов «по возможности» — может пропустить
запуск, а может позвать дважды (ADR-0035), поэтому обработчик обязан сам понимать, сделана
ли работа за этот период.

Период — не время вызова, а то, за что отвечает прогон: сутки у утренней сводки, сутки у
снимка состояния, час у проверки сроков. Ключ периода вычисляет сам обработчик, а
уникальность пары «задача + период» держит база: две функции, разбуженные одновременно,
не договорятся между собой, а вторая вставка упадёт.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.repos.base import Base, Timestamps, UUIDPrimaryKey


class JobRun(UUIDPrimaryKey, Timestamps, Base):
    """Один прогон одной задачи за один период."""

    __tablename__ = "job_runs"

    name: Mapped[str] = mapped_column(String(50), nullable=False)
    """Имя задачи: `morning-summary`, `daily-snapshot`, `deadline-check`."""

    period: Mapped[str] = mapped_column(String(20), nullable=False)
    """За что отвечает прогон: `2026-09-20` или `2026-09-20T14`."""

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False)
    """`running`, `done` или `failed`."""

    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    """Что задача сделала: числа, которые видно в сводке прогона. Свободная форма —
    у каждой задачи свои величины, и заводить под них столбцы значило бы менять схему
    вместе с каждой задачей."""

    error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        # Тот самый запрет двойной работы — и он частичный. Уникальны только удавшиеся и
        # идущие прогоны: неудачных за один период может быть сколько угодно, иначе одна
        # ошибка отменила бы задачу до конца суток, а вторая попытка падала бы уже на
        # записи о падении.
        Index(
            "uq_job_runs_name_period",
            "name",
            "period",
            unique=True,
            postgresql_where=text("status <> 'failed'"),
        ),
    )
