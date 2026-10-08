"""Привоз контрольной таблицы «Ижро»: шапка, строки, классы изменений (ТЗ 7).

Правила — из плана ввоза ORB-104 и счёта по настоящим таблицам заказчика (ADR-0025); здесь
они собраны в одну чистую функцию над уже прочитанной таблицей (`app.adapters.docx`).

1. **Шапка опознаётся по словам, а расхождение — отказ.** Обязательны четыре колонки:
   документ, содержание, срок, ответственный. Молчаливый сдвиг колонок даёт правдоподобные
   данные, и это самая дорогая ошибка ввоза.
2. **Строка-разделитель** — одна ячейка на всю ширину («СЕНТЯБРЬ»): месяц блока для
   перенесённых просрочек (`parse_due`).
3. **Год — из заголовка таблицы**, месяц — из ячейки срока.
4. **Плохая строка не останавливает привоз**: три нераспознанные не блокируют 161 хорошую.
   У каждой — номер, начало текста и причина кодом.
5. **Классы** (ТЗ 7): новые, без изменений, текст изменился, сменился ответственный, срок
   сдвинут, исчезли, не распознано. Ключ повтора — (документ, пункт, срок); строка с тем же
   документом и пунктом, но другим сроком — «срок сдвинут», а не новая.

Названия колонок настоящих таблиц в репозитории не записаны — таблицы лежат только у
заказчика (`data/README.md`). Поэтому слова шапки — по смыслу граф, и первый привоз
настоящего файла — проверка разборщика (риск 3 PLAN).
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum

from app.domain.dictionaries import OrganizationKind
from app.domain.errors import RuleViolationError
from app.domain.ijro import (
    MONTHS,
    DocumentKind,
    DuePrecision,
    DueYearSource,
    ExtensionKind,
    IjroSource,
    due_precision_for,
    extract_band,
    normalize_document_code,
    normalize_spaces,
    parse_due,
    split_responsible,
)

COARSE_DATES = frozenset({(12, 25)})
"""Отчётные даты, которые значат «до конца года» (ответ на Q31). Когда правило уйдёт в
справочник порогов, эта константа станет значением по умолчанию."""

RAW_PREVIEW_LENGTH = 200
"""Сколько знаков нераспознанной строки показать человеку — чтобы узнать её в Word."""


class ChangeClass(StrEnum):
    """Класс строки предпросмотра (ТЗ 7). Порядок объявления — порядок групп на экране."""

    NEW = "new"
    UNCHANGED = "unchanged"
    TEXT_CHANGED = "text_changed"
    RESPONSIBLE_CHANGED = "responsible_changed"
    DUE_MOVED = "due_moved"
    VANISHED = "vanished"
    UNRECOGNIZED = "unrecognized"


class Column(StrEnum):
    DOCUMENT = "document"
    CONTENT = "content"
    MECHANISM = "mechanism"
    DUE = "due"
    RESPONSIBLE = "responsible"
    STATE = "state"


REQUIRED = (Column.DOCUMENT, Column.CONTENT, Column.DUE, Column.RESPONSIBLE)

_HEADER_WORDS: dict[Column, tuple[str, ...]] = {
    Column.DOCUMENT: ("хужжат",),
    Column.MECHANISM: ("механизм",),
    Column.DUE: ("муддат",),
    Column.STATE: ("холат",),
    Column.CONTENT: ("мазмун", "топширик"),
    Column.RESPONSIBLE: ("масъул", "ижрочи"),
}
"""Слова граф после складывания узбекских букв. Порядок проверки важен: «Ижро муддати» и
«Ижро ҳолати» разбираются раньше, чем «ижрочи» ответственного, а «Топшириқ» — только
среди граф, которые не оказались документом."""

_FOLD = str.maketrans({"қ": "к", "ғ": "г", "ҳ": "х", "ў": "у", "ё": "е"})


def _fold(text: str) -> str:
    return normalize_spaces(text).lower().translate(_FOLD)


COLUMN_NAMES = {
    Column.DOCUMENT: "«Ҳужжат тури ва рақами»",
    Column.CONTENT: "«Топшириқ мазмуни»",
    Column.DUE: "«Ижро муддати»",
    Column.RESPONSIBLE: "«Масъул ижрочи»",
}


def detect_columns(header: Sequence[str]) -> dict[Column, int] | None:
    """Номера граф по шапке; `None` — это не шапка (нет хотя бы одной обязательной)."""
    folded = [_fold(cell) for cell in header]
    taken: set[int] = set()
    found: dict[Column, int] = {}
    for column, words in _HEADER_WORDS.items():
        for index, text in enumerate(folded):
            if index not in taken and any(word in text for word in words):
                found[column] = index
                taken.add(index)
                break
    return found if all(column in found for column in REQUIRED) else None


_YEAR = re.compile(r"(20\d{2})\s*(?:-?\s*йил|й\b|г\b|год)", re.IGNORECASE)
_DOCUMENT_CODE = re.compile(r"([A-ZА-ЯЁЎҚҒҲ]{1,5})\s*-\s*(\d+(?:[/-]\d+)?)")
_ISSUED = re.compile(r"(\d{1,2})\s*\.\s*(\d{1,2})\s*\.\s*(20\d{2})")
_MECHANISM = "амалга ошириш механизми"
_KIND_PREFIX = {
    "ПФ": DocumentKind.FARMON,
    "ПҚ": DocumentKind.QAROR,
    "ВМҚ": DocumentKind.QAROR,
    "ЎРҚ": DocumentKind.QONUN,
}
_KIND_WORD = {
    "фармон": DocumentKind.FARMON,
    "карор": DocumentKind.QAROR,
    "конун": DocumentKind.QONUN,
    "баён": DocumentKind.BAYON,
    "баен": DocumentKind.BAYON,
    "топширик": DocumentKind.TOPSHIRIQ,
}


def table_year(paragraphs: Iterable[str]) -> int | None:
    """Год из заголовка таблицы: «… Назорат жадвали 2026 йил»."""
    for text in paragraphs:
        match = _YEAR.search(text)
        if match:
            return int(match.group(1))
    return None


def guess_source(filename: str) -> IjroSource | None:
    """Источник по имени файла — подсказка для выбора, а не решение (Q33)."""
    name = filename.upper()
    if "АПП" in name:
        return IjroSource.LEGAL
    if "ВМ" in name:
        return IjroSource.VM
    if "ПА" in name or "АП " in name or name.startswith("АП"):
        return IjroSource.PA
    return None


@dataclass(frozen=True, slots=True)
class ParsedRow:
    """Строка таблицы, разобранная в поля источника (инвариант 4: только они)."""

    index: int
    """Номер строки в таблице — по нему человек находит её в Word."""

    document_raw: str
    document_code: str
    code_norm: str
    kind: DocumentKind
    issued_on: date | None
    band: str | None
    content: str
    mechanism: str | None
    due_raw: str | None
    due_on: date | None
    due_precision: DuePrecision
    due_year_source: DueYearSource | None
    block_label: str | None
    responsible_raw: str
    responsible_ours: str
    lead_raw: str | None
    state_raw: str | None

    @property
    def key(self) -> tuple[str, str | None, date | None]:
        return (self.code_norm, self.band, self.due_on)

    @property
    def text(self) -> str:
        return " ".join(part for part in (self.document_raw, self.content) if part)


@dataclass(frozen=True, slots=True)
class BadRow:
    index: int
    reason: str
    """Код причины: `row-too-short`, `document-unparsed`, `due-unparsed`,
    `responsible-empty`, `content-empty`, `duplicate-key`."""

    raw: str


@dataclass(frozen=True, slots=True)
class ParsedTable:
    table_year: int
    rows: tuple[ParsedRow, ...]
    bad: tuple[BadRow, ...]


def _document(paragraphs: Sequence[str]) -> tuple[str, str, DocumentKind, date | None]:
    raw = "\n".join(paragraphs)
    flat = normalize_spaces(" ".join(paragraphs))
    match = _DOCUMENT_CODE.search(flat)
    code = f"{match.group(1)}-{match.group(2)}" if match else (paragraphs[0] if paragraphs else "")
    kind = _KIND_PREFIX.get(match.group(1).upper(), DocumentKind.OTHER) if match else None
    if kind in (None, DocumentKind.OTHER):
        folded = _fold(flat)
        kind = next(
            (value for word, value in _KIND_WORD.items() if word in folded), DocumentKind.OTHER
        )
    issued: date | None = None
    if found := _ISSUED.search(flat):
        try:
            issued = date(int(found.group(3)), int(found.group(2)), int(found.group(1)))
        except ValueError:
            issued = None
    return raw, code[:120], kind or DocumentKind.OTHER, issued


def _month_only(raw: str, year: int) -> date | None:
    """Срок одним месяцем — «декабрь»: последний день месяца, точность «месяц» (V33)."""
    folded = _fold(raw)
    if re.search(r"\d", folded):
        return None
    for prefix, month in MONTHS.items():
        if prefix in folded:
            first_next = date(year + month // 12, month % 12 + 1, 1)
            return first_next - timedelta(days=1)
    return None


def _block_month(text: str) -> int | None:
    folded = _fold(text)
    return next((month for prefix, month in MONTHS.items() if prefix in folded), None)


def parse_table(
    paragraphs: Sequence[str],
    tables: Sequence[Sequence[Sequence[Sequence[str]]]],
    *,
    fallback_year: int,
    year: int | None = None,
) -> ParsedTable:
    """Строки всех таблиц файла с опознанной шапкой. Нет ни одной — отказ ввоза."""
    found_year = year or table_year(paragraphs) or fallback_year
    rows: list[ParsedRow] = []
    bad: list[BadRow] = []
    recognized = False
    number = 0

    for table in tables:
        columns: dict[Column, int] | None = None
        block_month: int | None = None
        block_label: str | None = None
        for cells in table:
            texts = [" ".join(cell) for cell in cells]
            if columns is None:
                columns = detect_columns(texts)
                continue
            if all(not text or text.strip().isdigit() for text in texts):
                continue  # нумерация граф «1 2 3 4 5 6 7» под шапкой и пустые строки
            filled = [text for text in texts if text]
            # Разделитель — одна ячейка на всю ширину (`gridSpan`): «СЕНТЯБРЬ».
            if len(cells) == 1 or (len(filled) == 1 and len(cells) <= 2):
                block_label = filled[0] if filled else None
                block_month = _block_month(block_label or "")
                continue
            number += 1
            parsed = _row(cells, columns, number, found_year, block_month, block_label)
            if isinstance(parsed, BadRow):
                bad.append(parsed)
            else:
                rows.append(parsed)
        recognized = recognized or columns is not None

    if not recognized:
        names = ", ".join(COLUMN_NAMES[column] for column in REQUIRED)
        raise RuleViolationError(
            "В таблице не найдена шапка контрольной таблицы",
            detail=f"Нужны графы {names}. Проверьте, что загружен «Назорат жадвали».",
        )
    return ParsedTable(table_year=found_year, rows=tuple(_unique(rows, bad)), bad=tuple(bad))


def _unique(rows: list[ParsedRow], bad: list[BadRow]) -> list[ParsedRow]:
    """Повтор строки байт в байт — один раз; тот же ключ с другим текстом — не распознано.

    Повтор в данных есть ровно один, и он байт в байт; ключ с другим текстом значил бы два
    разных поручения под одним пунктом и сроком — угадывать, какое из них настоящее, нельзя.
    """
    seen: dict[tuple[str, str | None, date | None], ParsedRow] = {}
    unique: list[ParsedRow] = []
    for row in rows:
        twin = seen.get(row.key)
        if twin is None:
            seen[row.key] = row
            unique.append(row)
        elif (twin.content, twin.responsible_raw) != (row.content, row.responsible_raw):
            bad.append(BadRow(row.index, "duplicate-key", row.text[:RAW_PREVIEW_LENGTH]))
    return unique


def _row(
    cells: Sequence[Sequence[str]],
    columns: dict[Column, int],
    index: int,
    year: int,
    block_month: int | None,
    block_label: str | None,
) -> ParsedRow | BadRow:
    raw_text = normalize_spaces(" ".join(" ".join(cell) for cell in cells))[:RAW_PREVIEW_LENGTH]
    if len(cells) <= max(columns.values()):
        return BadRow(index, "row-too-short", raw_text)

    def cell(column: Column) -> list[str]:
        position = columns.get(column)
        return list(cells[position]) if position is not None else []

    document = cell(Column.DOCUMENT)
    document_raw, code, kind, issued = _document(document)
    code_norm = normalize_document_code(" ".join(document))
    if not code_norm:
        return BadRow(index, "document-unparsed", raw_text)

    paragraphs = cell(Column.CONTENT)
    mechanism_paragraphs = cell(Column.MECHANISM)
    if Column.MECHANISM not in columns:
        at = next(
            (i for i, text in enumerate(paragraphs) if _fold(text).startswith(_MECHANISM)), None
        )
        if at is not None:
            heading = paragraphs[at][len(_MECHANISM) :].strip(" :.-")
            mechanism_paragraphs = ([heading] if heading else []) + paragraphs[at + 1 :]
            paragraphs = paragraphs[:at]
    content = normalize_spaces(" ".join(paragraphs))
    if not content:
        return BadRow(index, "content-empty", raw_text)
    mechanism = normalize_spaces(" ".join(mechanism_paragraphs)) or None

    due_raw = normalize_spaces(" ".join(cell(Column.DUE))) or None
    due_on: date | None = None
    precision = DuePrecision.EXACT
    year_source: DueYearSource | None = None
    if due_raw is not None:
        parsed = parse_due(due_raw, table_year=year, block_month=block_month)
        if parsed is not None:
            due_on, year_source = parsed
            precision = due_precision_for(due_on, coarse_dates=COARSE_DATES)
        elif (month_end := _month_only(due_raw, year)) is not None:
            due_on, precision, year_source = (
                month_end,
                DuePrecision.MONTH,
                DueYearSource.FROM_HEADER,
            )
        else:
            return BadRow(index, "due-unparsed", raw_text)

    responsible_raw = normalize_spaces(" ".join(cell(Column.RESPONSIBLE)))
    if not responsible_raw:
        return BadRow(index, "responsible-empty", raw_text)
    ours, theirs = split_responsible(responsible_raw)
    state_raw = normalize_spaces(" ".join(cell(Column.STATE))) or None

    return ParsedRow(
        index=index,
        document_raw=document_raw,
        document_code=code,
        code_norm=code_norm,
        kind=kind,
        issued_on=issued,
        band=extract_band(content),
        content=content,
        mechanism=mechanism,
        due_raw=due_raw[:100] if due_raw else None,
        due_on=due_on,
        due_precision=precision,
        due_year_source=year_source,
        block_label=block_label[:40] if block_label else None,
        responsible_raw=responsible_raw,
        responsible_ours=ours,
        lead_raw=theirs,
        state_raw=state_raw[:400] if state_raw else None,
    )


_ORG_NOISE = re.compile(r"[«»\"'`.,;:()]+")


def normalize_organization(name: str) -> str:
    """Ключ сравнения названий ведомств: регистр, кавычки, узбекские буквы.

    Названия в таблицах обрываются по-разному в зависимости от ширины ячейки
    (`IjroOrgAlias`); обрыв ключ не лечит — его запоминает псевдоним после первого привоза.
    """
    return normalize_spaces(_ORG_NOISE.sub(" ", _fold(name)))


def organization_kind(name: str) -> str:
    """Вид нового ведомства по слову в названии; без узнаваемого слова — «агентство»."""
    folded = _fold(name)
    if "вазирлиг" in folded or "министерств" in folded:
        return OrganizationKind.MINISTRY.value
    if "хокимлиг" in folded or "хокимият" in folded:
        return OrganizationKind.KHOKIMIYAT.value
    return OrganizationKind.AGENCY.value


# ---------------------------------------------------------------------------
# Сверка с реестром
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Existing:
    """Строка реестра в том виде, в каком её сверяет привоз — только поля источника."""

    id: uuid.UUID
    code_norm: str
    band: str | None
    due_on: date | None
    content: str
    mechanism: str | None
    responsible_raw: str
    source: str
    removed: bool


@dataclass(frozen=True, slots=True)
class Change:
    row: ParsedRow
    kind: ChangeClass
    assignment_id: uuid.UUID | None = None
    diff: tuple[str, str, str] | None = None
    """Поле, было, стало — для изменившегося текста или ответственного."""

    due_from: date | None = None
    suggested: ExtensionKind | None = None


@dataclass(frozen=True, slots=True)
class Comparison:
    changes: tuple[Change, ...]
    vanished: tuple[uuid.UUID, ...] = field(default=())


def _diff(row: ParsedRow, old: Existing) -> tuple[ChangeClass, tuple[str, str, str] | None]:
    if normalize_spaces(old.content) != row.content:
        return ChangeClass.TEXT_CHANGED, ("content", old.content, row.content)
    if normalize_spaces(old.mechanism or "") != (row.mechanism or ""):
        return ChangeClass.TEXT_CHANGED, ("mechanism", old.mechanism or "", row.mechanism or "")
    if normalize_spaces(old.responsible_raw) != row.responsible_raw:
        return ChangeClass.RESPONSIBLE_CHANGED, (
            "responsible_raw",
            old.responsible_raw,
            row.responsible_raw,
        )
    return ChangeClass.UNCHANGED, None


def compare(rows: Sequence[ParsedRow], existing: Sequence[Existing], *, source: str) -> Comparison:
    """Классы строк таблицы против реестра (ТЗ 7).

    «Исчезли» — только строки того же источника и не снятые с контроля: таблица Кабмина не
    обязана перечислять поручения Администрации, а снятое с контроля из таблиц и уходит.
    """
    by_key = {(each.code_norm, each.band, each.due_on): each for each in existing}
    matched: set[uuid.UUID] = set()
    changes: list[Change] = []
    pending: list[ParsedRow] = []

    for row in rows:
        old = by_key.get(row.key)
        if old is None:
            pending.append(row)
            continue
        matched.add(old.id)
        kind, diff = _diff(row, old)
        changes.append(Change(row=row, kind=kind, assignment_id=old.id, diff=diff))

    for row in pending:
        # Тот же документ и пункт, другой срок — перенос. Из нескольких свободных берётся
        # ближайший по сроку: у регулярного поручения пункт повторяется по месяцам.
        candidates = [
            each
            for each in existing
            if each.id not in matched
            and (each.code_norm, each.band) == (row.code_norm, row.band)
            and each.due_on is not None
            and row.due_on is not None
        ]
        if not candidates:
            changes.append(Change(row=row, kind=ChangeClass.NEW))
            continue
        assert row.due_on is not None
        target = row.due_on
        old = min(
            candidates,
            key=lambda each: (abs(((each.due_on or target) - target).days), str(each.id)),
        )
        matched.add(old.id)
        _, diff = _diff(row, old)
        assert old.due_on is not None
        changes.append(
            Change(
                row=row,
                kind=ChangeClass.DUE_MOVED,
                assignment_id=old.id,
                diff=diff,
                due_from=old.due_on,
                suggested=(
                    ExtensionKind.EXTENSION if row.due_on > old.due_on else ExtensionKind.CORRECTION
                ),
            )
        )

    vanished = tuple(
        each.id
        for each in existing
        if each.id not in matched and each.source == source and not each.removed
    )
    changes.sort(key=lambda change: change.row.index)
    return Comparison(changes=tuple(changes), vanished=vanished)
