"""Файлы: проверка загрузки, ссылка на просмотр, тело файла локального хранилища.

Загрузка идёт браузером прямо в хранилище по подписанной ссылке (`app.services.files`). Тело
файла через API — только у локального хранилища: разработка и сервер агентства, где лимита
функции нет. Отдача — с `Content-Disposition: inline`, чтобы PDF открывался в браузере.
"""

from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import SessionDep, StorageDep
from app.api.security import Assistant, CurrentUser
from app.api.transaction import transactional_router
from app.domain.errors import RuleViolationError
from app.domain.files import MAX_SIZE
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
    file_id: uuid.UUID, request: Request, user: Assistant, session: SessionDep, storage: StorageDep
) -> None:
    content = await request.body()
    if len(content) > MAX_SIZE:
        raise RuleViolationError("Файл больше допустимого размера")
    await service.put_content(session, storage=storage, file_id=file_id, content=content)


@router.post(
    "/files/{file_id}/complete",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Файл загружен: проверить и показать",
)
async def complete(
    file_id: uuid.UUID, user: Assistant, session: SessionDep, storage: StorageDep
) -> None:
    await service.complete(session, storage=storage, file_id=file_id)


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
