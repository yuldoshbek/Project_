"""Регламентные задания.

Каждое обязано быть **идемпотентным**: повторный запуск на тех же данных не производит
второго действия (CLAUDE.md, инвариант 6). Это не пожелание к аккуратности — воркер
перезапускается при выкладке, задание может выполниться дважды, и без идемпотентности
второй прогон шлёт второе напоминание.

Напоминания и эскалация приходят с ORB-038 и ORB-039, снимки состояния — с ORB-063,
отчёты — с ORB-044: каждое заводит своё, а не дописывает сюда заранее пустые заглушки.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.preview import (
    ConversionError,
    ConverterUnavailableError,
    DocumentConverter,
    create_document_converter,
)
from app.adapters.storage import FileStorage, StorageError, create_file_storage
from app.domain.documents import PreviewState, preview_key
from app.repos.models import Document, DocumentVersion
from app.settings import Settings, get_settings
from app.workers.context import job, job_scope

logger = structlog.get_logger(__name__)


async def build_preview(ctx: dict[str, Any], version_id: str) -> bool:
    """Строит производный PDF для офисного вложения (ТЗ 6.6, ADR-0009).

    Фоном, а не в запросе: LibreOffice открывает тридцатимегабайтную таблицу десятки
    секунд, и загрузка, которая столько думает, выглядит зависшей.
    """
    settings: Settings = ctx.get("settings") or get_settings()
    async with job_scope("build_preview", job_id=ctx.get("job_id")) as session:
        return await build_preview_once(
            session,
            create_file_storage(settings),
            create_document_converter(settings),
            uuid.UUID(version_id),
        )


async def build_preview_once(
    session: AsyncSession,
    storage: FileStorage,
    converter: DocumentConverter,
    version_id: uuid.UUID,
) -> bool:
    """Само действие, отдельно от обвязки задания.

    **Идемпотентно** (CLAUDE.md, инвариант 6): у версии, предпросмотр которой уже готов,
    задание ничего не делает. Второй запуск не строит второй PDF и не перезаписывает
    готовый — а запускается оно дважды легко, потому что первая попытка могла упасть
    после записи в хранилище, но до фиксации транзакции.

    **Отсутствие версии — повод повторить, а не забыть.** Задание ставится из обработчика
    запроса, до фиксации его транзакции (`app.adapters.queue`), и «версии нет» здесь чаще
    означает «ещё не зафиксирована», чем «удалена». Разница между повтором и отказом —
    это разница между тридцатью секундами задержки и файлом, который никогда не получит
    предпросмотра.
    """
    version = await session.get(DocumentVersion, version_id)
    if version is None:
        raise LookupError(f"версия {version_id} не найдена — возможно, ещё не зафиксирована")

    if version.preview_state == PreviewState.READY.value:
        logger.info("build_preview_already_done", version=str(version_id))
        return False

    document = await session.get(Document, version.document_id)
    if document is None:
        raise LookupError(f"документ версии {version_id} не найден")

    try:
        source = await storage.get(version.storage_key)
        pdf = await converter.to_pdf(source, filename=document.name)
    except ConversionError as failure:
        # Файл не преобразуется и не преобразуется никогда: помечаем и уходим. Повтор
        # только занял бы очередь и трижды записал в лог одно и то же.
        version.preview_state = PreviewState.FAILED.value
        await session.flush()
        logger.warning("build_preview_failed", version=str(version_id), error=str(failure))
        return False
    except (ConverterUnavailableError, StorageError):
        # Состояние не меняется: «готовится» — это правда, преобразователь вернётся.
        raise

    key = preview_key(version.storage_key)
    await storage.put(key, pdf, content_type="application/pdf")

    version.preview_key = key
    version.preview_state = PreviewState.READY.value
    await session.flush()

    logger.info("build_preview_done", version=str(version_id), size=len(pdf))
    return True


build_preview_job = job(build_preview)
