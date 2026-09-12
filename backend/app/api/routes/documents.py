"""Вложения к проектам и задачам (ТЗ 6.6).

**Содержимое через этот API не проходит — ни в одну сторону, кроме загрузки.** Скачивание
и предпросмотр отвечают подписанной ссылкой, по которой браузер идёт в хранилище сам
(ADR-0009). Отдавать файл через приложение означало бы держать обработчик занятым всё
время передачи; три одновременных скачивания по пятьдесят мегабайт останавливают систему
для обоих пользователей.

Ссылка отдаётся **телом ответа, а не перенаправлением**. Перенаправление выглядит удобнее
ровно до первой попытки: браузер не понесёт заголовок с токеном на чужой адрес, а если
понесёт — унесёт его в хранилище. Ссылку берёт интерфейс и открывает её сам, и тогда
токен остаётся там, где он выдан.

Читать может любой вошедший, загружать и удалять — только помощник (ADR-0011).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Depends, File, Form, Query, Request, UploadFile
from pydantic import BaseModel

from app.api.deps import QueueDep, ScannerDep, SessionDep, SettingsDep, StorageDep
from app.api.security import Assistant, get_active_user
from app.api.transaction import transactional_router
from app.domain.documents import DocumentTarget, PreviewState, megabytes
from app.domain.errors import RuleViolationError
from app.repos.models import Document, DocumentVersion
from app.services import documents as service
from app.settings import Settings

router = transactional_router(tags=["вложения"], dependencies=[Depends(get_active_user)])

MULTIPART_OVERHEAD = 4096
"""Запас на границы частей и имена полей в теле multipart."""


def limits_from(settings: Settings) -> service.Limits:
    return service.Limits(
        max_bytes=settings.upload_max_bytes,
        prefix=settings.s3_prefix,
        link_lifetime=timedelta(seconds=settings.download_link_seconds),
        restricted_link_lifetime=timedelta(seconds=settings.restricted_link_seconds),
    )


async def refuse_oversized_body(request: Request, settings: SettingsDep) -> None:
    """Отказ по объявленному размеру — до чтения тела.

    Зависимости разбираются раньше, чем разбирается тело запроса, и это единственное
    место, где отказ обходится без приёма файла целиком. Без него пятисотмегабайтный файл
    сначала полностью приедет на диск, и лишь потом ему скажут, что он велик.

    Заявленному размеру не верят: настоящий проверяется по принятому содержимому. Это не
    дублирование — здесь отсекают честную ошибку, там ловят неверный заголовок.
    """
    declared = request.headers.get("content-length")
    if declared is None or not declared.isdigit():
        return
    limit = settings.upload_max_bytes
    if int(declared) > limit + MULTIPART_OVERHEAD:
        raise RuleViolationError(
            f"Файл весит {megabytes(int(declared))} МБ, а предел — {megabytes(limit)} МБ. "
            "Положите файл в общую папку и приложите ссылку"
        )


class VersionResponse(BaseModel):
    id: uuid.UUID
    number: int
    size_bytes: int
    content_type: str
    sha256: str
    uploaded_at: datetime
    uploaded_by: uuid.UUID | None
    preview_state: PreviewState

    @classmethod
    def of(cls, version: DocumentVersion) -> VersionResponse:
        return cls(
            id=version.id,
            number=version.number,
            size_bytes=version.size_bytes,
            content_type=version.content_type,
            sha256=version.sha256,
            uploaded_at=version.uploaded_at,
            uploaded_by=version.uploaded_by,
            preview_state=PreviewState(version.preview_state),
        )


class DocumentResponse(BaseModel):
    """Документ и его текущая версия.

    Ключ хранения наружу не выдаётся ни здесь, ни где-либо ещё: по нему видно устройство
    бакета, а сделать с ним без подписи всё равно ничего нельзя. Отпечаток, наоборот,
    выдаётся — по нему интерфейс отличает «тот же файл» от «файл с тем же именем».
    """

    id: uuid.UUID
    entity_type: DocumentTarget
    entity_id: uuid.UUID
    name: str
    current_version: int
    created_at: datetime
    version: VersionResponse

    @classmethod
    def of(cls, document: Document, version: DocumentVersion) -> DocumentResponse:
        return cls(
            id=document.id,
            entity_type=DocumentTarget(document.entity_type),
            entity_id=document.entity_id,
            name=document.name,
            current_version=document.current_version,
            created_at=document.created_at,
            version=VersionResponse.of(version),
        )


class UploadResponse(BaseModel):
    """Ответ на загрузку.

    `created = false` означает, что этот файл уже приложен и новой версии не появилось.
    Без такого признака интерфейс показал бы «загружено», а список остался бы прежним —
    и человек нажал бы ещё раз.
    """

    created: bool
    document: DocumentResponse


class LinkResponse(BaseModel):
    url: str
    expires_in: int
    """Сколько секунд ссылка действует. Интерфейс по нему решает, когда просить новую."""

    filename: str


@router.get("/documents", response_model=list[DocumentResponse], summary="Вложения записи")
async def list_documents(
    session: SessionDep,
    entity_type: Annotated[DocumentTarget, Query(description="Проект или задача")],
    entity_id: Annotated[uuid.UUID, Query()],
) -> list[DocumentResponse]:
    views = await service.list_for(session, entity_type, entity_id)
    return [DocumentResponse.of(view.document, view.version) for view in views]


@router.post(
    "/documents",
    response_model=UploadResponse,
    status_code=201,
    summary="Загрузить файл",
    dependencies=[Depends(refuse_oversized_body)],
)
async def upload_document(
    session: SessionDep,
    settings: SettingsDep,
    storage: StorageDep,
    scanner: ScannerDep,
    queue: QueueDep,
    user: Assistant,
    entity_type: Annotated[DocumentTarget, Form(description="Проект или задача")],
    entity_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File(description="Содержимое файла")],
) -> UploadResponse:
    """Повторная загрузка того же имени даёт версию; того же содержимого — ничего."""
    result = await service.upload(
        session,
        storage,
        scanner,
        queue,
        service.UploadDraft(
            entity_type=entity_type,
            entity_id=entity_id,
            filename=file.filename or "",
            content=await file.read(),
        ),
        uploader=user,
        limits=limits_from(settings),
    )
    return UploadResponse(
        created=result.created,
        document=DocumentResponse.of(result.document, result.version),
    )


@router.get(
    "/documents/{document_id}/versions",
    response_model=list[VersionResponse],
    summary="Версии документа",
)
async def list_versions(document_id: uuid.UUID, session: SessionDep) -> list[VersionResponse]:
    versions = await service.versions_of(session, document_id)
    return [VersionResponse.of(version) for version in versions]


@router.get(
    "/documents/{document_id}/link", response_model=LinkResponse, summary="Ссылка на содержимое"
)
async def document_link(
    document_id: uuid.UUID,
    session: SessionDep,
    settings: SettingsDep,
    storage: StorageDep,
    version: Annotated[int | None, Query(description="Номер версии; по умолчанию текущая")] = None,
    inline: Annotated[bool, Query(description="Показать в окне, а не сохранить")] = False,
) -> LinkResponse:
    """Подписанная ссылка с ограниченным сроком жизни.

    Для проекта с грифом срок короче, а сама выдача попадает в журнал — решает это
    сервис, а не роутер (CLAUDE.md, инвариант 1).
    """
    limits = limits_from(settings)
    document = await service.get(session, document_id)
    chosen = await service.version_of(session, document, version)

    link = await service.link_for(
        session, storage, document=document, version=chosen, inline=inline, limits=limits
    )
    return LinkResponse(
        url=link.url,
        expires_in=int(link.lifetime.total_seconds()),
        filename=link.filename,
    )


@router.delete("/documents/{document_id}", status_code=204, summary="Удалить вложение")
async def delete_document(document_id: uuid.UUID, session: SessionDep, user: Assistant) -> None:
    """Удаление мягкое: версии остаются, файл из списка уходит (ADR-0009)."""
    await service.delete(session, document_id)
