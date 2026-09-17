"""Вложения: сценарии использования.

Порядок действий при загрузке выбран так, чтобы **ни одна неудача не оставляла следа**.

1. Проверяется имя, формат, размер и подпись содержимого — всё, на что не нужны ни база,
   ни сеть. Отказ на этом шаге не стоит ничего.
2. Проверяется антивирусом. До того, как файл окажется где бы то ни было: в хранилище, в
   базе, в интерфейсе. Заражённый файл не сохраняется вовсе — не «сохраняется и
   прячется» (Q7).
3. Считается отпечаток и ищется такое же содержимое у того же владельца. Нашлось —
   возвращается найденное, и ничего не создаётся.
4. Заводится документ или новая версия существующего, содержимое кладётся в хранилище.

Последний шаг единственный, который может оставить мусор: если запись в базу не
удастся, объект в хранилище останется без ссылки на него. Обратный порядок хуже — тогда
в базе оказалась бы версия, которой нет в хранилище, и список вложений показывал бы файл,
который не открывается. Лишний объект в бакете не виден никому и убирается регламентным
заданием (ORB-047); строка в базе без файла видна всем и чинится только руками.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.antivirus import AntivirusUnavailableError, VirusScanner
from app.adapters.queue import JobQueue
from app.adapters.storage import FileStorage, StorageError
from app.domain.clock import now_utc
from app.domain.documents import (
    MAX_SIGNATURE_BYTES,
    DocumentError,
    DocumentTarget,
    PreviewState,
    check_signature,
    check_size,
    extension_of,
    kind_of,
    normalize_name,
    storage_key,
)
from app.domain.errors import (
    ExternalServiceError,
    NotFoundError,
    RuleViolationError,
)
from app.repos.models import Document, DocumentVersion, Project, Task, User

logger = structlog.get_logger(__name__)

PREVIEW_JOB = "build_preview"


@dataclass(frozen=True, slots=True)
class Limits:
    """Пределы и сроки из настроек. Сервис не читает их сам — иначе его не проверить."""

    max_bytes: int
    prefix: str
    link_lifetime: timedelta


@dataclass(frozen=True, slots=True)
class UploadDraft:
    entity_type: DocumentTarget
    entity_id: uuid.UUID
    filename: str
    content: bytes


@dataclass(frozen=True, slots=True)
class UploadResult:
    """Что получилось из загрузки.

    `created` отвечает на вопрос, который иначе задаёт пользователь: «я нажал, а ничего
    не появилось». Не появилось потому, что этот файл уже приложен, — и интерфейс обязан
    сказать это, а не молча ничего не показать.
    """

    document: Document
    version: DocumentVersion
    created: bool


@dataclass(frozen=True, slots=True)
class DocumentView:
    document: Document
    version: DocumentVersion


@dataclass(frozen=True, slots=True)
class Link:
    """Выданная ссылка.

    Срок возвращается вместе со ссылкой, а не вычисляется вызывающим по настройкам: для
    закрытого проекта он другой, и вызывающий, повторяющий это правило у себя, однажды
    повторит его неверно — и покажет «ссылка действует 5 минут» там, где она умрёт через
    минуту.
    """

    url: str
    lifetime: timedelta
    filename: str


_TABLE: dict[DocumentTarget, type[Project] | type[Task]] = {
    DocumentTarget.PROJECT: Project,
    DocumentTarget.TASK: Task,
}


async def target_exists(
    session: AsyncSession, entity_type: DocumentTarget, entity_id: uuid.UUID
) -> bool:
    model = _TABLE[entity_type]
    return await session.scalar(select(model.id).where(model.id == entity_id)) is not None


async def list_for(
    session: AsyncSession, entity_type: DocumentTarget, entity_id: uuid.UUID
) -> list[DocumentView]:
    """Вложения записи — по одной строке на документ, с текущей версией.

    Удалённые не показываются: у документа, в отличие от реплики, нет соседей, чей смысл
    ломается от пропуска. Версии удалённого документа остаются в базе (ADR-0009) и
    нужны разбору, а не списку.
    """
    if not await target_exists(session, entity_type, entity_id):
        raise NotFoundError("Запись не найдена")

    rows = await session.execute(
        select(Document, DocumentVersion)
        .join(
            DocumentVersion,
            (DocumentVersion.document_id == Document.id)
            & (DocumentVersion.number == Document.current_version),
        )
        .where(
            Document.entity_type == entity_type.value,
            Document.entity_id == entity_id,
            Document.deleted_at.is_(None),
        )
        .order_by(Document.name)
    )
    return [DocumentView(document=document, version=version) for document, version in rows]


async def get(session: AsyncSession, document_id: uuid.UUID) -> Document:
    document = await session.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise NotFoundError("Вложение не найдено")
    return document


async def versions_of(session: AsyncSession, document_id: uuid.UUID) -> list[DocumentVersion]:
    """История документа, от свежей версии к первой."""
    await get(session, document_id)
    return list(
        await session.scalars(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.number.desc())
        )
    )


async def version_of(
    session: AsyncSession, document: Document, number: int | None
) -> DocumentVersion:
    """Версия по номеру; без номера — текущая."""
    wanted = document.current_version if number is None else number
    version = await session.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id, DocumentVersion.number == wanted
        )
    )
    if version is None:
        raise NotFoundError(f"Версия {wanted} не найдена")
    return version


async def upload(
    session: AsyncSession,
    storage: FileStorage,
    scanner: VirusScanner,
    queue: JobQueue | None,
    draft: UploadDraft,
    *,
    uploader: User,
    limits: Limits,
) -> UploadResult:
    """Загрузка файла. Порядок шагов объяснён в описании модуля."""
    try:
        name = normalize_name(draft.filename)
        kind = kind_of(name)
        check_size(len(draft.content), limit=limits.max_bytes)
        check_signature(kind, draft.content[:MAX_SIGNATURE_BYTES])
    except DocumentError as error:
        raise RuleViolationError(str(error)) from error

    if not draft.content:
        raise RuleViolationError("Файл пустой — загружать нечего")

    if not await target_exists(session, draft.entity_type, draft.entity_id):
        raise NotFoundError("Запись не найдена")

    await _scan(draft.content, scanner=scanner, name=name)

    digest = hashlib.sha256(draft.content).hexdigest()

    same = await _same_content(session, draft.entity_type, draft.entity_id, digest)
    if same is not None:
        document, version = same
        logger.info("document_already_attached", document=str(document.id), name=document.name)
        return UploadResult(document=document, version=version, created=False)

    document, is_new = await _document_for(session, draft.entity_type, draft.entity_id, name)
    number = 1 if is_new else document.current_version + 1
    await session.flush()  # нужен идентификатор документа: он входит в ключ хранения

    key = storage_key(
        prefix=limits.prefix,
        target=draft.entity_type,
        entity_id=str(draft.entity_id),
        document_id=str(document.id),
        version=number,
        ext=extension_of(name),
    )

    try:
        await storage.put(key, draft.content, content_type=kind.content_type)
    except StorageError as error:
        raise ExternalServiceError("Хранилище файлов недоступно, загрузка не выполнена") from error

    version = DocumentVersion(
        document_id=document.id,
        number=number,
        storage_key=key,
        size_bytes=len(draft.content),
        content_type=kind.content_type,
        sha256=digest,
        uploaded_by=uploader.id,
        preview_state=kind.preview.value,
    )
    session.add(version)
    document.current_version = number
    await session.flush()

    if queue is not None and kind.preview is PreviewState.PENDING:
        await queue.enqueue(PREVIEW_JOB, str(version.id), job_id=f"preview:{version.id}")

    logger.info(
        "document_uploaded",
        document=str(document.id),
        version=number,
        size=len(draft.content),
        scanner=scanner.name,
    )
    return UploadResult(document=document, version=version, created=True)


async def _scan(content: bytes, *, scanner: VirusScanner, name: str) -> None:
    """Антивирусная проверка. Недоступность запрещает загрузку, а не разрешает её."""
    try:
        result = await scanner.scan(content)
    except AntivirusUnavailableError as error:
        logger.error("antivirus_unavailable", error=str(error))
        raise ExternalServiceError(
            "Антивирус недоступен, загрузка файлов временно невозможна"
        ) from error

    if result.is_clean:
        return

    # Имя найденного наружу не идёт: по нему подбирают то, что антивирус пропустит.
    logger.warning("document_rejected_infected", name=name, signature=result.signature)
    raise RuleViolationError(
        "Файл не прошёл антивирусную проверку и не загружен. "
        "Проверьте его своим антивирусом или возьмите файл из первоисточника"
    )


async def _same_content(
    session: AsyncSession, entity_type: DocumentTarget, entity_id: uuid.UUID, digest: str
) -> tuple[Document, DocumentVersion] | None:
    """Ищет такое же содержимое у того же владельца (ADR-0009).

    Владелец, а не документ: тот же файл, загруженный второй раз под другим именем, —
    это тот же файл. Две карточки на одно содержимое означают, что правку внесут в одну
    из них, а откроют другую.
    """
    row = (
        await session.execute(
            select(Document, DocumentVersion)
            .join(DocumentVersion, DocumentVersion.document_id == Document.id)
            .where(
                Document.entity_type == entity_type.value,
                Document.entity_id == entity_id,
                Document.deleted_at.is_(None),
                DocumentVersion.sha256 == digest,
            )
            .order_by(DocumentVersion.number.desc())
            .limit(1)
        )
    ).first()
    return None if row is None else (row[0], row[1])


async def _document_for(
    session: AsyncSession, entity_type: DocumentTarget, entity_id: uuid.UUID, name: str
) -> tuple[Document, bool]:
    """Документ с таким именем у этого владельца — существующий либо новый.

    Второе значение говорит, какой из двух. Оно возвращается отсюда, а не выясняется по
    `document.id is None` у вызывающего: у только что добавленного объекта
    идентификатора ещё нет, но это свойство сохранения, а не ответ на вопрос «это новый
    документ» — и первая же перестановка `flush` сделала бы такую проверку неверной,
    ничего не сломав заметно.
    """
    document = await session.scalar(
        select(Document).where(
            Document.entity_type == entity_type.value,
            Document.entity_id == entity_id,
            Document.name == name,
            Document.deleted_at.is_(None),
        )
    )
    if document is not None:
        return document, False

    fresh = Document(
        entity_type=entity_type.value, entity_id=entity_id, name=name, current_version=1
    )
    session.add(fresh)
    return fresh, True


async def link_for(
    session: AsyncSession,
    storage: FileStorage,
    *,
    document: Document,
    version: DocumentVersion,
    inline: bool,
    limits: Limits,
) -> Link:
    """Подписанная ссылка на содержимое (ADR-0009).

    Срок жизни один для всех файлов. Раньше их было два: файл проекта с грифом получал
    минуту вместо пяти, а выдача записывалась в журнал действием `DOWNLOADED`. И то, и
    другое защищало от пересылки ссылки — а пересылать её теперь некому, ссылку получают
    те же двое ([ADR-0024](../../../docs/adr/ADR-0024-share-externally.md),
    [ADR-0011](../../../docs/adr/ADR-0011-two-user-scope.md)).

    `share_externally` здесь не спрашивается намеренно. Ссылка живёт внутри периметра:
    её открывает вошедший пользователь, а не Google, SETA и не внешняя модель. Точек
    выхода наружу пять, и эта в их число не входит.
    """
    key = version.storage_key
    filename = document.name
    content_type = version.content_type

    if inline and version.preview_state == PreviewState.READY.value and version.preview_key:
        # Показывается производный PDF, а не исходная таблица: браузер её не откроет.
        key = version.preview_key
        filename = f"{document.name}.pdf"
        content_type = "application/pdf"

    lifetime = limits.link_lifetime

    try:
        url = await storage.link(
            key,
            filename=filename,
            content_type=content_type,
            inline=inline,
            lifetime=lifetime,
        )
    except StorageError as error:
        raise ExternalServiceError("Хранилище файлов недоступно") from error

    return Link(url=url, lifetime=lifetime, filename=filename)


async def delete(session: AsyncSession, document_id: uuid.UUID) -> None:
    """Мягкое удаление документа (ADR-0009).

    Содержимое из хранилища не убирается: удаление мягкое ровно затем, чтобы историю
    можно было восстановить, а восстанавливать нечего, если файлы уже стёрты. Физическая
    очистка — отдельное регламентное задание (ORB-047), и у него другой повод: место, а
    не решение пользователя.
    """
    document = await get(session, document_id)
    document.deleted_at = now_utc()
    await session.flush()


async def delete_for(
    session: AsyncSession, storage: FileStorage, entity_type: DocumentTarget, entity_id: uuid.UUID
) -> None:
    """Убирает вложения записи насовсем — вместе с содержимым.

    Здесь удаление настоящее, а не мягкое, и это не противоречит предыдущему: мягко
    удаляют документ, когда запись остаётся. Когда уходит сама запись, хранить её файлы
    негде — владельца больше нет, и найти их будет нечем.
    """
    documents = list(
        await session.scalars(
            select(Document).where(
                Document.entity_type == entity_type.value, Document.entity_id == entity_id
            )
        )
    )
    if not documents:
        return

    ids = [document.id for document in documents]
    versions = list(
        await session.scalars(select(DocumentVersion).where(DocumentVersion.document_id.in_(ids)))
    )
    keys = [version.storage_key for version in versions]
    keys += [version.preview_key for version in versions if version.preview_key]

    for document in documents:
        await session.delete(document)
    await session.flush()

    try:
        await storage.delete(keys)
    except StorageError as error:
        # Запись уже удалена, и откатывать её из-за недоступного хранилища не стоит:
        # осиротевшие объекты уберёт регламентное задание, а несогласованная база —
        # проблема без владельца.
        logger.error("storage_cleanup_failed", error=str(error), keys=len(keys))
