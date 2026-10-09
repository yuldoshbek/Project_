"""Поиск по всем разделам — правила строки запроса (ТЗ 6, допущение V19).

Поиск — по части названия или номера, без учёта регистра. Самое важное здесь —
письменность. Содержание поручений Ижро хранится как в источнике, на узбекской кириллице
(CLAUDE.md, «Язык»), а на телефоне по умолчанию латинская раскладка: помощник набирает
«kosmik», а в поручении «Космик». Поэтому запрос ищется в двух написаниях — как набран и
переписанный другой письменностью. Переписывание грубое и только для поиска: «x» и «h» —
разные буквы узбекского (х и ҳ), и это различие сохраняется, а написание ФИО и данных оно
не трогает никогда.
"""

from __future__ import annotations

from enum import StrEnum

MIN_LENGTH = 2
"""Короче двух знаков запрос не ищется: одна буква совпадает с половиной базы."""

MAX_LENGTH = 100
"""Длиннее — это не запрос, а вставленный абзац; лишнее отрезается."""

PER_KIND = 5
"""Сколько находок одного вида показать. Больше — уже список раздела, а не поиск."""


class HitKind(StrEnum):
    """Что нашлось. По виду экран решает, какую карточку открыть."""

    PROGRAM = "program"
    PROJECT = "project"
    TASK = "task"
    IJRO = "ijro"
    LETTER = "letter"
    ORGANIZATION = "organization"
    AGREEMENT = "agreement"
    IDEA = "idea"
    PREPARATION = "preparation"


# Апострофы узбекской латиницы набирают по-разному: ʻ, ʼ, ’, ‘, ` и простой '. В данных и
# в запросе они приводятся к одному, иначе «oʻzbek» не найдёт «o'zbek». Данные сворачивает
# функция базы `search_fold` (миграция 0010_search) — с теми же знаками.
APOSTROPHES = "ʻʼ’‘`"
APOSTROPHE = "'"

_LATIN_PAIRS = (
    ("o'", "ў"),
    ("g'", "ғ"),
    ("sh", "ш"),
    ("ch", "ч"),
    ("yo", "ё"),
    ("yu", "ю"),
    ("ya", "я"),
)
_LATIN_LETTERS = {
    "a": "а",
    "b": "б",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "ҳ",
    "i": "и",
    "j": "ж",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "q": "қ",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "v": "в",
    "x": "х",
    "y": "й",
    "z": "з",
    "'": "ъ",
}
_CYRILLIC_LETTERS = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "ғ": "g'",
    "д": "d",
    "е": "e",
    "ё": "yo",
    "ж": "j",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "қ": "q",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ў": "o'",
    "ф": "f",
    "х": "x",
    "ҳ": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sh",
    "ъ": "'",
    "ы": "i",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def normalize(query: str) -> str:
    """Строка запроса как её сравнивает база: нижний регистр, один вид апострофа, пробелы."""
    text = " ".join(query.split())[:MAX_LENGTH].lower()
    for mark in APOSTROPHES:
        text = text.replace(mark, APOSTROPHE)
    return text


def _to_cyrillic(text: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(text):
        pair = text[index : index + 2]
        found = next((cyr for lat, cyr in _LATIN_PAIRS if lat == pair), None)
        if found:
            out.append(found)
            index += 2
            continue
        out.append(_LATIN_LETTERS.get(text[index], text[index]))
        index += 1
    return "".join(out)


def _to_latin(text: str) -> str:
    return "".join(_CYRILLIC_LETTERS.get(char, char) for char in text)


def spellings(query: str) -> tuple[str, ...]:
    """Написания, в которых ищется запрос: как набран и другой письменностью.

    Пусто — запрос короче `MIN_LENGTH` после нормализации и не ищется вовсе. Номера и
    цифры от переписывания не меняются, поэтому «ПФ-155» найдётся и как «pf-155».
    """
    text = normalize(query)
    if len(text) < MIN_LENGTH:
        return ()
    other = _to_cyrillic(text) if text.isascii() else _to_latin(text)
    return (text,) if other == text else (text, other)


def like_pattern(text: str) -> str:
    """Шаблон «содержит» для LIKE: знаки % и _ из запроса ищутся буквально."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
