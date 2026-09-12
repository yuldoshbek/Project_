"""Вложения: логический документ и его версии (ADR-0009).

Две таблицы, а не одна. Одна означала бы, что «Смета.xlsx» и «Смета.xlsx (версия 2)» —
две независимые записи, и вопрос «какая последняя» решался бы сравнением времени загрузки
у файлов с одинаковым именем. Здесь у документа есть имя и номер текущей версии, а у
версии — содержимое: размер, тип, отпечаток и ключ в хранилище.

Ссылка на проект или задачу внешним ключом не закрыта — как и у комментариев,
`entity_id` указывает то на одну таблицу, то на другую. Целостность держит удаление:
сервис уносит вложения вместе с записью, к которой они относились.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.documents import (
    NAME_MAX_LENGTH,
    SHA256_LENGTH,
    DocumentTarget,
    PreviewState,
)
from app.repos.base import Base, Timestamps, UUIDPrimaryKey
from app.repos.models.audit import Auditable

TARGETS = ", ".join(f"'{target.value}'" for target in DocumentTarget)
PREVIEW_STATES = ", ".join(f"'{state.value}'" for state in PreviewState)


class Document(Auditable, UUIDPrimaryKey, Timestamps, Base):
    """Логический файл, прикреплённый к проекту или задаче (ТЗ 6.6)."""

    __tablename__ = "documents"

    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # CITEXT: «Смета.xlsx» и «смета.xlsx» — один документ. Регистр в имени файла ставят
    # не думая, и два документа из-за заглавной буквы — ровно та путаница, ради которой
    # версии и заводились.
    name: Mapped[str] = mapped_column(CITEXT, nullable=False)

    # Номер последней версии. Денормализация намеренная: «какая сейчас» спрашивается в
    # каждом списке вложений, а считать максимум по версиям ради одного числа — лишний
    # запрос на каждую строку.
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Удаление мягкое (ADR-0009): версии остаются, чтобы история проекта не рвалась.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def audit_is_classified(self) -> bool:
        """Имя файла в журнал изменений не попадает — никогда.

        «Смета по объекту в Кашкадарье.xlsx» рассказывает о проекте столько же, сколько
        его название, а журнал переживает и удаление проекта, и очистку хранилища. Для
        проекта с грифом это означало бы, что содержимое расползлось в таблицу, из
        которой его уже не вычистить (ADR-0007).

        Ответить «закрыт ли гриф» точнее отсюда нельзя: свойство читается в момент
        сохранения, а владелец лежит в другой таблице, и обращение к нему здесь — это
        запрос к базе из обработчика сохранения. Поэтому закрыто всегда, а не иногда:
        журналу нужно «кто и когда», а «как назывался файл» лежит в самой записи и
        никуда не девается — удаление мягкое.
        """
        return True

    __table_args__ = (
        CheckConstraint(f"entity_type IN ({TARGETS})", name="entity_type_is_known"),
        CheckConstraint(
            f"char_length(name) BETWEEN 1 AND {NAME_MAX_LENGTH}", name="name_length_is_sane"
        ),
        # Одно имя у одного владельца — один документ. Ограничение частичное: удалённый
        # документ освобождает имя, иначе файл, удалённый по ошибке, нельзя загрузить
        # заново под тем же именем — а это первое, что человек попробует.
        Index(
            "uq_documents_entity_type_entity_id_name",
            "entity_type",
            "entity_id",
            "name",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        Index("ix_documents_entity_type_entity_id", "entity_type", "entity_id"),
    )


class DocumentVersion(UUIDPrimaryKey, Base):
    """Одно содержимое документа в один момент времени.

    `Timestamps` не используется: версия неизменяема. `updated_at` у неё — поле, которое
    никогда не заполнится, а `created_at` называется `uploaded_at`, потому что это время
    загрузки, а не время строки.
    """

    __tablename__ = "document_versions"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)

    storage_key: Mapped[str] = mapped_column(String(500), nullable=False, unique=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)

    # Отпечаток содержимого. По нему отсекается повторная загрузка того же файла — и по
    # нему же потом проверяют, что в хранилище лежит именно то, что загружали.
    sha256: Mapped[str] = mapped_column(String(SHA256_LENGTH), nullable=False)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Предпросмотр. `preview_key` заполняется только для производного PDF: у файла,
    # который браузер показывает сам, производной нет и быть не должно — это была бы
    # вторая копия того же документа.
    preview_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PreviewState.PENDING.value
    )
    preview_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        UniqueConstraint("document_id", "number", name="uq_document_versions_document_id_number"),
        CheckConstraint(f"preview_state IN ({PREVIEW_STATES})", name="preview_state_is_known"),
        CheckConstraint("size_bytes > 0", name="size_is_positive"),
        CheckConstraint("number > 0", name="number_is_positive"),
        # Поиск повторной загрузки: «есть ли уже такое содержимое у этого владельца».
        Index("ix_document_versions_sha256", "sha256"),
    )
