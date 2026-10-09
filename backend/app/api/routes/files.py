"""Файлы: проверка загрузки, ссылка на просмотр, тело файла локального хранилища.

Загрузка идёт браузером прямо в хранилище по подписанной ссылке (`app.services.files`). Тело
файла через API — только у локального хранилища: разработка и сервер агентства, где лимита
функции нет. Отдача — с `Content-Disposition: inline`, чтобы PDF открывался в браузере.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.deps import SessionDep, StorageDep
from app.api.security import CurrentUser
from app.api.transaction import transactional_router
from app.domain.errors import RuleViolationError
from app.domain.files import MAX_SIZE, NAME_MAX_LENGTH, PHOTO_OWNERS, FileOwner
from app.services import files as service

router = transactional_router(tags=["файлы"])


class LinkOut(BaseModel):
    url: str


@router.put(
    "/files/{file_id}/content",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Тело файла — только для локального хранилища",
)
async def put_content(
    file_id: uuid.UUID,
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    storage: StorageDep,
) -> None:
    content = await request.body()
    if len(content) > MAX_SIZE:
        raise RuleViolationError("Файл больше допустимого размера")
    # Кто вправе класть файл, решает сценарий по владельцу: презентацию — помощник, фото
    # из Захвата — оба (`app.domain.files.may_upload`).
    await service.put_content(session, user=user, storage=storage, file_id=file_id, content=content)


@router.post(
    "/files/{file_id}/complete",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Файл загружен: проверить и показать",
)
async def complete(
    file_id: uuid.UUID, user: CurrentUser, session: SessionDep, storage: StorageDep
) -> None:
    await service.complete(session, user=user, storage=storage, file_id=file_id)


@router.get("/files/{file_id}/link", response_model=LinkOut, summary="Ссылка на просмотр")
async def read_link(
    file_id: uuid.UUID, user: CurrentUser, session: SessionDep, storage: StorageDep
) -> LinkOut:
    return LinkOut(url=await service.link(session, storage=storage, file_id=file_id))


@router.get("/files/{file_id}/content", summary="Файл локального хранилища")
async def read_content(
    file_id: uuid.UUID, user: CurrentUser, session: SessionDep, storage: StorageDep
) -> FileResponse:
    path, content_type, name = await service.local_file(session, storage=storage, file_id=file_id)
    return FileResponse(
        path,
        media_type=content_type,
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(name)}"},
    )


class NewPhotoRequest(BaseModel):
    owner_type: FileOwner
    owner_id: uuid.UUID
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    content_type: str = Field(max_length=120)
    size: int


class PhotoUploadOut(BaseModel):
    url: str
    method: str
    headers: dict[str, str]


class StartedPhotoOut(BaseModel):
    file_id: uuid.UUID
    upload: PhotoUploadOut


@router.post(
    "/files/photos",
    response_model=StartedPhotoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Фото к записи из Захвата: ссылка на загрузку",
)
async def start_photo(
    body: NewPhotoRequest, user: CurrentUser, session: SessionDep, storage: StorageDep
) -> StartedPhotoOut:
    started = await service.start_photo(
        session,
        user=user,
        storage=storage,
        owner=body.owner_type,
        owner_id=body.owner_id,
        name=body.name,
        content_type=body.content_type,
        size=body.size,
    )
    return StartedPhotoOut(
        file_id=started.file_id,
        upload=PhotoUploadOut(
            url=started.upload.url, method=started.upload.method, headers=started.upload.headers
        ),
    )


class PhotoOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime


@router.get("/files/photos", response_model=list[PhotoOut], summary="Фото записи")
async def list_photos(
    owner_type: Annotated[FileOwner, Query()],
    owner_id: Annotated[uuid.UUID, Query()],
    session: SessionDep,
) -> list[PhotoOut]:
    if owner_type not in PHOTO_OWNERS:
        return []
    found = await service.photos(session, owner=owner_type, owner_id=owner_id)
    return [PhotoOut(id=photo.id, name=photo.name, created_at=photo.created_at) for photo in found]
