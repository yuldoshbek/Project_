"""Файлы и версии презентаций: ссылка на загрузку → проверка → просмотр (ADR-0009, ТЗ 3.5).

Загрузка в три шага, чтобы большая презентация шла в хранилище мимо API:

1. помощник просит ссылку — API проверяет тип и размер, заводит строку файла «загружается» и
   версию презентации, отдаёт подписанную ссылку;
2. браузер кладёт файл по ссылке сам;
3. API проверяет, что файл лёг и размер совпал, — и только тогда версия видна.

Замечание на слайд оставляют оба (инвариант 13: роль подписывает, а не запрещает); отметку
«исправлено» ставит помощник — исправляет он.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.storage import FileStorage, LocalStorage, UploadTarget
from app.domain.errors import NotFoundError, RuleViolationError, check_version
from app.domain.files import FileOwner, FileState, check_upload, storage_key
from app.domain.preparations import COMMENT_MAX_LENGTH, VersionState
from app.repos.models import Preparation, PresentationVersion, SlideComment, StoredFile, User


@dataclass(frozen=True, slots=True)
class StartedUpload:
    version_id: uuid.UUID
    file_id: uuid.UUID
    upload: UploadTarget


async def _file(session: AsyncSession, file_id: uuid.UUID) -> StoredFile:
    found = await session.get(StoredFile, file_id)
    if found is None:
        raise NotFoundError("Файл не найден: его могли удалить")
    return found


async def start_version(
    session: AsyncSession,
    *,
    user: User,
    storage: FileStorage,
    preparation_id: uuid.UUID,
    name: str,
    content_type: str,
    size: int,
) -> StartedUpload:
    """Новая версия презентации: номер по порядку и ссылка на загрузку файла."""
    if await session.get(Preparation, preparation_id) is None:
        raise NotFoundError("Подготовка не найдена: её могли удалить")
    cleaned = check_upload(name=name, content_type=content_type, size=size)
    last = await session.scalar(
        select(func.max(PresentationVersion.number)).where(
            PresentationVersion.preparation_id == preparation_id
        )
    )
    version_id = uuid.uuid4()
    file_id = uuid.uuid4()
    key = storage_key(FileOwner.PRESENTATION_VERSION, version_id, file_id, content_type)
    # Ссылку просим до записи: не настроенное хранилище должно отказать раньше, чем в базе
    # появится версия без файла.
    target = storage.upload_target(key, file_id=str(file_id), content_type=content_type)
    session.add(
        StoredFile(
            id=file_id,
            owner_type=FileOwner.PRESENTATION_VERSION.value,
            owner_id=version_id,
            name=cleaned,
            content_type=content_type,
            size=size,
            storage_key=key,
            state=FileState.PENDING.value,
            uploaded_by=user.id,
        )
    )
    await session.flush()
    session.add(
        PresentationVersion(
            id=version_id,
            preparation_id=preparation_id,
            number=(last or 0) + 1,
            file_id=file_id,
            state=VersionState.REVIEW.value,
            uploaded_by=user.id,
        )
    )
    await session.flush()
    return StartedUpload(version_id=version_id, file_id=file_id, upload=target)


def write_local(storage: FileStorage, stored: StoredFile, content: bytes) -> None:
    """Тело файла для локального хранилища: у него загрузка идёт через API."""
    if not isinstance(storage, LocalStorage):
        raise RuleViolationError("Файл загружается прямо в хранилище по выданной ссылке")
    if stored.state != FileState.PENDING.value:
        raise RuleViolationError("Файл уже загружен")
    if len(content) != stored.size:
        raise RuleViolationError("Размер файла не совпал с заявленным — загрузите его заново")
    storage.write(stored.storage_key, content)


async def put_content(
    session: AsyncSession, *, storage: FileStorage, file_id: uuid.UUID, content: bytes
) -> None:
    write_local(storage, await _file(session, file_id), content)


async def complete(session: AsyncSession, *, storage: FileStorage, file_id: uuid.UUID) -> None:
    """Файл лёг — проверяем размер в хранилище и показываем версию."""
    stored = await _file(session, file_id)
    if stored.state == FileState.STORED.value:
        return
    size = await storage.size(stored.storage_key)
    if size is None:
        raise RuleViolationError("Файл ещё не загружен — повторите загрузку")
    if size != stored.size:
        raise RuleViolationError("Размер файла не совпал с заявленным — загрузите его заново")
    stored.state = FileState.STORED.value


async def link(session: AsyncSession, *, storage: FileStorage, file_id: uuid.UUID) -> str:
    stored = await _file(session, file_id)
    if stored.state != FileState.STORED.value:
        raise RuleViolationError("Файл ещё не загружен")
    return storage.download_url(stored.storage_key, file_id=str(file_id))


async def local_file(
    session: AsyncSession, *, storage: FileStorage, file_id: uuid.UUID
) -> tuple[str, str, str]:
    """Путь, тип и имя файла локального хранилища — для отдачи через API."""
    stored = await _file(session, file_id)
    if not isinstance(storage, LocalStorage) or stored.state != FileState.STORED.value:
        raise NotFoundError("Файл недоступен")
    return str(storage.path(stored.storage_key)), stored.content_type, stored.name


async def set_version_state(
    session: AsyncSession,
    *,
    preparation_id: uuid.UUID,
    version_id: uuid.UUID,
    state: VersionState,
    version: int,
) -> None:
    found = await session.get(PresentationVersion, version_id)
    if found is None or found.preparation_id != preparation_id:
        raise NotFoundError("Версия не найдена: её могли удалить")
    check_version(expected=version, actual=found.version)
    found.state = state.value


async def add_comment(
    session: AsyncSession,
    *,
    user: User,
    preparation_id: uuid.UUID,
    version_id: uuid.UUID,
    slide: int,
    text: str,
) -> uuid.UUID:
    found = await session.get(PresentationVersion, version_id)
    if found is None or found.preparation_id != preparation_id:
        raise NotFoundError("Версия не найдена: её могли удалить")
    body = " ".join(text.split())
    if not body:
        raise RuleViolationError("Напишите замечание")
    if len(body) > COMMENT_MAX_LENGTH:
        raise RuleViolationError(f"Замечание длиннее {COMMENT_MAX_LENGTH} знаков")
    if slide < 1:
        raise RuleViolationError("Номер слайда — с единицы")
    comment = SlideComment(version_id=version_id, slide=slide, text=body, author_id=user.id)
    session.add(comment)
    await session.flush()
    return comment.id


async def fix_comment(
    session: AsyncSession,
    *,
    preparation_id: uuid.UUID,
    comment_id: uuid.UUID,
    fixed: bool,
    version: int,
) -> None:
    """«Исправлено» — в последней загруженной версии; снять — если отметили по ошибке."""
    comment = await session.get(SlideComment, comment_id)
    if comment is None:
        raise NotFoundError("Замечание не найдено")
    check_version(expected=version, actual=comment.version)
    latest = await session.scalar(
        select(PresentationVersion.id)
        .join(StoredFile, StoredFile.id == PresentationVersion.file_id)
        .where(
            PresentationVersion.preparation_id == preparation_id,
            StoredFile.state == FileState.STORED.value,
        )
        .order_by(PresentationVersion.number.desc())
        .limit(1)
    )
    comment.fixed_in_version_id = latest if fixed else None


async def versions(
    session: AsyncSession, *, preparation_id: uuid.UUID, zone: ZoneInfo
) -> list[dict[str, Any]]:
    """Загруженные версии презентации — новые первыми, с замечаниями."""
    rows = await session.execute(
        select(PresentationVersion, StoredFile, User.role)
        .join(StoredFile, StoredFile.id == PresentationVersion.file_id)
        .outerjoin(User, User.id == PresentationVersion.uploaded_by)
        .where(
            PresentationVersion.preparation_id == preparation_id,
            StoredFile.state == FileState.STORED.value,
        )
        .order_by(PresentationVersion.number.desc())
    )
    found = list(rows.tuples())
    numbers = {each.id: each.number for each, _, _ in found}
    comments: dict[uuid.UUID, list[dict[str, Any]]] = {}
    if found:
        comment_rows = await session.execute(
            select(SlideComment, User.role)
            .outerjoin(User, User.id == SlideComment.author_id)
            .where(SlideComment.version_id.in_(list(numbers)))
            .order_by(SlideComment.slide, SlideComment.created_at, SlideComment.id)
        )
        for comment, role in comment_rows:
            comments.setdefault(comment.version_id, []).append(
                {
                    "id": comment.id,
                    "slide": comment.slide,
                    "text": comment.text,
                    "author": role,
                    "created_at": comment.created_at,
                    "fixed_in": numbers.get(comment.fixed_in_version_id)
                    if comment.fixed_in_version_id
                    else None,
                    "version": comment.version,
                }
            )
    return [
        {
            "id": version.id,
            "number": version.number,
            "state": version.state,
            "file": {
                "id": stored.id,
                "name": stored.name,
                "size": stored.size,
                "content_type": stored.content_type,
            },
            "uploaded_at": version.created_at,
            "uploaded_by": role,
            "comments": comments.get(version.id, []),
            "version": version.version,
        }
        for version, stored, role in found
    ]
