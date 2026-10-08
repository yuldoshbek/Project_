"""Файлы и версии презентаций (ТЗ 3.5, ADR-0009).

`stored_files` — файл в хранилище: имя, тип, размер, ключ, кто загрузил. Строка появляется
до файла (ссылка на загрузку выдана) и становится «сохранён», когда API проверил, что файл
лёг: так в интерфейс не попадает ссылка на пустое место.

`presentation_versions` — версия презентации доклада: номер, PDF, статус (на просмотре, на
доработке, принята). `slide_comments` — замечание на слайд: номер слайда, текст, автор,
отметка «исправлено» и в какой версии.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.files import NAME_MAX_LENGTH, FileOwner, FileState
from app.domain.preparations import VersionState
from app.repos.base import Base, Timestamps, UUIDPrimaryKey, Versioned
from app.repos.models.audit import Auditable


def _values(enum: type[FileOwner | FileState | VersionState]) -> str:
    return ", ".join(f"'{item.value}'" for item in enum)


class StoredFile(Auditable, UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "stored_files"

    owner_type: Mapped[str] = mapped_column(String(30), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(400), nullable=False, unique=True)
    state: Mapped[str] = mapped_column(String(10), nullable=False, default=FileState.PENDING.value)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(f"owner_type IN ({_values(FileOwner)})", name="owner_type_is_known"),
        CheckConstraint(f"state IN ({_values(FileState)})", name="state_is_known"),
        Index("ix_stored_files_owner_type_owner_id", "owner_type", "owner_id"),
    )


class PresentationVersion(Auditable, Versioned, UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "presentation_versions"

    preparation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("preparations.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stored_files.id", ondelete="RESTRICT"), nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(10), nullable=False, default=VersionState.REVIEW.value
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("preparation_id", "number"),
        CheckConstraint(f"state IN ({_values(VersionState)})", name="state_is_known"),
    )


class SlideComment(Auditable, Versioned, UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "slide_comments"

    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("presentation_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    slide: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    fixed_in_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("presentation_versions.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint("slide >= 1", name="slide_is_positive"),
        Index("ix_slide_comments_version_id", "version_id"),
    )
