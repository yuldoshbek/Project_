"""Вложения: что считается одним документом, что — новой версией, что вообще не примут.

Три правила, и все три существуют ради одной беды — «у меня было три Сметы, какая из них
последняя».

**Одно имя у одного владельца — один документ.** Повторная загрузка «Сметы.xlsx» к тому
же проекту даёт вторую версию, а не второй документ. Иначе список вложений превращается в
свалку одноимённых файлов, и последний приходится искать по времени загрузки, которое в
списке обычно не показывают.

**Одно содержимое — одна версия.** Тот же файл, загруженный второй раз, не порождает
ничего: версия, не отличающаяся от предыдущей ни байтом, — это не история, а шум, который
делает историю нечитаемой. Сравнение по sha256, а не по имени и размеру: два разных
документа одинакового размера — обычное дело.

**Принимается не всё.** Проверяется расширение **и** первые байты, а не заявленный
клиентом тип. Заголовок `Content-Type` пишет тот, кто загружает, и `application/pdf` в нём
не мешает файлу быть исполняемым. Размер и список типов — параметры настройки (Q7:
50 МБ, офисные форматы и изображения), но значения по умолчанию живут здесь: настройка,
которой забыли дать значение, не должна означать «принимать всё».
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

MEGABYTE = 1024 * 1024

DEFAULT_MAX_UPLOAD_MB = 50
"""Предел размера вложения по умолчанию (OPEN-QUESTIONS Q7).

В мегабайтах, а не в байтах: это значение правит человек в файле настроек, и
`52428800` он проверить глазами не может — а `50` может.
"""

NAME_MAX_LENGTH = 255
"""Длина имени файла. Столько же, сколько позволяет файловая система на выгрузке."""

SHA256_LENGTH = 64


class DocumentTarget(StrEnum):
    """К чему прикреплён документ.

    Реплики здесь нет, хотя ТЗ 6.6 их называет: реплика удаляется мягко, и у файла,
    привязанного к удалённой реплике, не остаётся никого, кто отвечал бы за его судьбу, —
    показывать нельзя, удалять нельзя, ссылки вести некуда. Вложения к репликам заводятся
    вместе с формой реплики на карточках (ORB-018, ORB-022), где этот вопрос решается
    вместе с тем, как удалённая реплика выглядит.
    """

    PROJECT = "project"
    TASK = "task"


class PreviewState(StrEnum):
    """Что показывать вместо файла, не скачивая его (ТЗ 6.6).

    `NATIVE` — файл показывается сам: браузер умеет PDF и изображения. Для остального
    рядом кладётся производный PDF, и до его появления состояние честно называется
    «готовится»: пустое место в интерфейсе читается как поломка.
    """

    NATIVE = "native"
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class FileKind:
    """Формат, который система принимает.

    `signatures` — пары «смещение, байты». Пустой набор означает формат без
    опознавательной подписи: у простого текста её нет и быть не может, и требовать её —
    значит не принимать текстовые файлы вовсе.
    """

    extension: str
    content_type: str
    signatures: tuple[tuple[int, bytes], ...]
    preview: PreviewState


ZIP = ((0, b"PK\x03\x04"), (0, b"PK\x05\x06"), (0, b"PK\x07\x08"))
"""Документы Open XML и OpenDocument — это zip-архивы, других подписей у них нет."""

OLE2 = ((0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),)
"""Старые форматы Microsoft Office — контейнер OLE2."""

_OFFICE = PreviewState.PENDING

KINDS: tuple[FileKind, ...] = (
    FileKind("pdf", "application/pdf", ((0, b"%PDF-"),), PreviewState.NATIVE),
    FileKind("jpg", "image/jpeg", ((0, b"\xff\xd8\xff"),), PreviewState.NATIVE),
    FileKind("jpeg", "image/jpeg", ((0, b"\xff\xd8\xff"),), PreviewState.NATIVE),
    FileKind("png", "image/png", ((0, b"\x89PNG\r\n\x1a\n"),), PreviewState.NATIVE),
    FileKind("gif", "image/gif", ((0, b"GIF87a"), (0, b"GIF89a")), PreviewState.NATIVE),
    FileKind("webp", "image/webp", ((0, b"RIFF"), (8, b"WEBP")), PreviewState.NATIVE),
    FileKind("txt", "text/plain; charset=utf-8", (), PreviewState.NATIVE),
    FileKind(
        "docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ZIP,
        _OFFICE,
    ),
    FileKind(
        "xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ZIP,
        _OFFICE,
    ),
    FileKind(
        "pptx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ZIP,
        _OFFICE,
    ),
    FileKind("odt", "application/vnd.oasis.opendocument.text", ZIP, _OFFICE),
    FileKind("ods", "application/vnd.oasis.opendocument.spreadsheet", ZIP, _OFFICE),
    FileKind("odp", "application/vnd.oasis.opendocument.presentation", ZIP, _OFFICE),
    FileKind("doc", "application/msword", OLE2, _OFFICE),
    FileKind("xls", "application/vnd.ms-excel", OLE2, _OFFICE),
    FileKind("ppt", "application/vnd.ms-powerpoint", OLE2, _OFFICE),
    FileKind("rtf", "application/rtf", ((0, b"{\\rtf"),), _OFFICE),
    FileKind("csv", "text/csv; charset=utf-8", (), _OFFICE),
)
"""Белый список (Q7: офисные форматы и изображения).

**SVG в нём нет намеренно.** Это не картинка, а размеченный документ со сценариями
внутри, и открывается он не просмотрщиком, а браузером. Файл раздаётся по ссылке из
хранилища — то есть с чужого для приложения адреса, но всё же нашего, — и сценарий внутри
рисунка выполнялся бы там. Ради возможности приложить схему это слишком дорого.

Исполняемых и архивных форматов нет по той же причине: «положить архив с чем угодно
внутри» отменяет весь список разом.
"""

BY_EXTENSION: dict[str, FileKind] = {kind.extension: kind for kind in KINDS}

MAX_SIGNATURE_BYTES = max(
    (offset + len(signature) for kind in KINDS for offset, signature in kind.signatures),
    default=0,
)
"""Сколько байтов достаточно прочитать, чтобы опознать формат."""

_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
_SPACES = re.compile(r"\s+")


class DocumentError(Exception):
    """Файл не годится. Текст сообщения адресован тому, кто его загружает."""


def normalize_name(raw: str) -> str:
    """Имя файла, пригодное к хранению и к выгрузке обратно.

    Путь отбрасывается: браузеры некоторых версий и загрузка папкой присылают
    `C:\\Users\\...\\Смета.xlsx`, и это имя нельзя ни показать, ни сохранить.

    Нормализация Unicode — не косметика: «ё» приходит с macOS разложенной на «е» и две
    точки, и такое имя не совпадёт с набранным на Windows ни в поиске, ни в проверке
    «тот же документ». Внешне оба выглядят одинаково — расхождение обнаруживается только
    тем, что у одного файла оказалось две карточки.
    """
    name = unicodedata.normalize("NFC", raw)
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = _SPACES.sub(" ", _UNSAFE.sub("", name)).strip(" .")

    if not name:
        raise DocumentError("Имя файла пустое или состоит из недопустимых знаков")
    if len(name) > NAME_MAX_LENGTH:
        raise DocumentError(f"Имя файла длиннее {NAME_MAX_LENGTH} знаков")
    return name


def extension_of(name: str) -> str:
    """Расширение в нижнем регистре, без точки. У файла без расширения — пустая строка."""
    _, dot, extension = name.rpartition(".")
    return extension.lower() if dot else ""


def kind_of(name: str) -> FileKind:
    """Формат по имени файла.

    Отказ называет расширение и перечисляет допустимые: сообщение «недопустимый тип файла»
    заставляет угадывать, а угадывать тут нечего.
    """
    extension = extension_of(name)
    kind = BY_EXTENSION.get(extension)
    if kind is None:
        allowed = ", ".join(sorted(BY_EXTENSION))
        shown = f"«{extension}»" if extension else "без расширения"
        raise DocumentError(f"Файлы {shown} не принимаются. Допустимые форматы: {allowed}")
    return kind


def check_signature(kind: FileKind, head: bytes) -> None:
    """Сверяет начало файла с подписью формата.

    Проверяется содержимое, а не заявленный тип: расширение и заголовок `Content-Type`
    пишет тот, кто загружает. Совпадение подписи не доказывает, что внутри именно то, что
    обещано, — на это есть антивирус; оно лишь отсекает «переименовал и загрузил».
    """
    if not kind.signatures:
        return
    if any(head[offset : offset + len(mark)] == mark for offset, mark in kind.signatures):
        return
    raise DocumentError(
        f"Содержимое файла не похоже на «{kind.extension}». "
        "Возможно, файлу поменяли расширение — загрузите его в исходном формате"
    )


def check_size(size: int, *, limit: int) -> None:
    """Предел размера. Сообщение называет и предел, и то, сколько весит файл."""
    if size <= limit:
        return
    raise DocumentError(
        f"Файл весит {megabytes(size)} МБ, а предел — {megabytes(limit)} МБ. "
        "Положите файл в общую папку и приложите ссылку"
    )


def megabytes(size: int) -> str:
    """Размер в мегабайтах, с одним знаком после запятой и запятой вместо точки."""
    return f"{size / 1024 / 1024:.1f}".replace(".", ",")


def storage_key(
    *, prefix: str, target: DocumentTarget, entity_id: str, document_id: str, version: int, ext: str
) -> str:
    """Ключ версии в хранилище (ADR-0009).

    Владелец входит в путь, хотя для поиска не нужен — по ключу восстанавливается, чему
    файл принадлежал. Это единственный способ разобраться в содержимом бакета, когда база
    недоступна, а именно тогда в него и заглядывают.
    """
    suffix = f".{ext}" if ext else ""
    return f"{prefix}/{target.value}/{entity_id}/{document_id}/v{version}{suffix}"


def preview_key(key: str) -> str:
    """Ключ производного PDF. Лежит рядом с версией, а не в отдельном бакете."""
    return f"{key}.preview.pdf"
