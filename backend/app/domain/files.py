"""Файлы: что можно загрузить и как это называется в хранилище (блок 2, ADR-0009).

Файл загружается браузером прямо в хранилище по подписанной ссылке: тело запроса к функции
Vercel ограничено 4,5 МБ, и презентация доклада через API не прошла бы (ARCHITECTURE, «Файлы»).
API выдаёт ссылку на загрузку, потом проверяет, что файл лёг, и только тогда показывает его.

Здесь — правила без хранилища: белый список типов, предельный размер, ключ.
"""

from __future__ import annotations

import re
import uuid
from enum import StrEnum

from app.domain.errors import RuleViolationError

MAX_SIZE = 50 * 1024 * 1024
"""50 МБ — по умолчанию ADR-0009: презентация доклада с картами весит 10–30 МБ."""

NAME_MAX_LENGTH = 255

ALLOWED_TYPES = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.ms-powerpoint": ".ppt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}
"""Что приходит в работе с докладами: PDF для просмотра, исходник презентации, документы,
картинки. Исполняемое и архивы не принимаются — антивируса в системе нет (снят)."""


class FileState(StrEnum):
    """Загружается — ссылка выдана, файла ещё нет; сохранён — файл проверен в хранилище."""

    PENDING = "pending"
    STORED = "stored"


class FileOwner(StrEnum):
    """Чему принадлежит файл. Закрытый набор: по нему собирается обратная ссылка."""

    PRESENTATION_VERSION = "presentation_version"


_UNSAFE = re.compile(r"[\\/:*?\"<>|\x00-\x1f]+")


def clean_name(name: str) -> str:
    """Имя файла для показа и скачивания: без путей и управляющих знаков."""
    value = _UNSAFE.sub("_", name).strip(" .")
    if not value:
        raise RuleViolationError("У файла нет имени")
    return value[-NAME_MAX_LENGTH:]


def check_upload(*, name: str, content_type: str, size: int) -> str:
    """Проверка до выдачи ссылки: тип из белого списка, размер в пределе. Возвращает имя."""
    cleaned = clean_name(name)
    if content_type not in ALLOWED_TYPES:
        raise RuleViolationError(
            "Такой тип файла не принимается",
            detail="Подходят PDF, PowerPoint, Word, Excel, PNG и JPEG",
        )
    if size <= 0:
        raise RuleViolationError("Файл пустой")
    if size > MAX_SIZE:
        raise RuleViolationError(f"Файл больше {MAX_SIZE // (1024 * 1024)} МБ — сожмите PDF")
    return cleaned


def storage_key(
    owner: FileOwner, owner_id: uuid.UUID, file_id: uuid.UUID, content_type: str
) -> str:
    """Ключ в хранилище: по нему видно, чьё это, но не видно имени — оно в базе.

    Имя файла в ключ не входит: «Доклад Кабмину о засухе.pdf» в адресе хранилища — это
    утечка содержания через журналы прокси и истории браузера.
    """
    return f"{owner.value}/{owner_id}/{file_id}{ALLOWED_TYPES[content_type]}"
