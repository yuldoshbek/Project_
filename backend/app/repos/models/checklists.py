"""Чек-листы и теги задач.

Две разные вещи в одном файле, потому что обе описывают одну задачу изнутри и появились
одним тикетом (ORB-015). Общее у них — и то, и другое живёт **не в задаче**: чек-лист
строками, теги связью. Список подзадач в текстовом поле не даёт отметить пункт, а теги
строкой через запятую не дают собрать задачи по тегу — тот самый вопрос, ради которого
теги и заводятся (ТЗ 6.2).
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.checklists import TAG_MAX_LENGTH
from app.repos.base import Base, Timestamps, UUIDPrimaryKey
from app.repos.models.audit import Auditable


class TaskChecklistItem(Auditable, UUIDPrimaryKey, Timestamps, Base):
    """Пункт чек-листа задачи (ТЗ 6.2).

    Журналируется наравне с задачей: «кто отметил пункт выполненным» — тот же вопрос, что
    «кто поменял статус», и по поручению он задаётся всерьёз. Инвариант 4 из CLAUDE.md
    требует, чтобы каждое изменение задачи попадало в журнал, а пункт чек-листа — это
    задача, а не примечание к ней.
    """

    __tablename__ = "task_checklist_items"

    # Пункт без задачи не существует: он и есть её часть. Удаление задачи уносит
    # чек-лист с собой — оставлять пункты сиротами не для кого.
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )

    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Порядок задаёт человек: пункты идут по ходу работы, а не по времени добавления.
    # «Согласовать» раньше «подписать», даже если вписали их наоборот.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (Index("ix_task_checklist_items_task_id_sort_order", "task_id", "sort_order"),)


class Tag(UUIDPrimaryKey, Timestamps, Base):
    """Тег — общее слово, которым помечают задачи из разных проектов.

    Не наследует `DictionaryEntry`: у тега нет ни технического кода, ни трёх названий. Он
    и не справочник в смысле ТЗ 7 — его не ведёт администратор, он появляется от ввода.

    Тип `citext`, а не `text`: «ДЗЗ» и «дзз» — один тег. Уникальность без учёта регистра
    обеспечивается типом столбца, а не проверкой в коде: проверку обходит первый же
    импорт, а тип — никто. Проверено на кириллице и узбекской кириллице: сравнение
    учитывает регистр обеих.
    """

    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)

    __table_args__ = (
        # Длину задаёт ограничение, а не тип: `citext` длины не принимает. Без него тег
        # становится местом, куда вставляют абзац, и список тегов перестаёт читаться.
        CheckConstraint(f"char_length(name) BETWEEN 1 AND {TAG_MAX_LENGTH}", name="name_length"),
    )


class TaskTag(Auditable, UUIDPrimaryKey, Timestamps, Base):
    """Пометка задачи тегом."""

    __tablename__ = "task_tags"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False
    )
    # Тег остаётся в словаре, пока им помечена хоть одна задача: удаление тега из-под
    # задач стёрло бы пометку, которую человек ставил осознанно. Та же причина, по
    # которой организация-партнёр не удаляется из-под проекта.
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tags.id", ondelete="RESTRICT"), nullable=False
    )

    __table_args__ = (
        # Один тег на задаче один раз. Имя не задаётся: соглашение из `repos.base`
        # строит его по столбцам, а переданное имя вытеснило бы его целиком.
        UniqueConstraint("task_id", "tag_id"),
        # «Какие задачи помечены этим тегом» — второй вопрос, и он главный: ради него
        # теги и существуют.
        Index("ix_task_tags_tag_id", "tag_id"),
    )
