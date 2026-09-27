"""Разбор строки задачи (ТЗ 7) — примеры утверждённого экрана, перенесённые с правилами.

Это все примеры из `frontend/src/sections/tasks/parse.test.ts`, на которых экран «Задачи»
утверждён. Расходиться с ними разбор сервера не имеет права: одна фраза должна давать
один срок и на экране, и в захвате с телефона.

Сегодня в примерах — пятница 25.09.2026: на ней видно правило «день недели — ближайший
впереди» и «конец недели — пятница».
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domain.capture import ParsedLine, parse_line

TODAY = date(2026, 9, 25)  # пятница

PEOPLE: list[tuple[object, str]] = [
    ("p-karimov", "Каримов А."),
    ("p-yusupova", "Юсупова Д."),
    ("p-rakhimov", "Рахимов Ш."),
    ("p-tursunov", "Турсунов Б."),
    ("p-abdullaeva", "Абдуллаева Н."),
]

TYPE_CODES = frozenset(
    {
        "technical_spec",
        "review_and_endorse",
        "approval",
        "cabinet_submission",
        "analytical_note",
        "site_visit",
        "request_or_survey",
        "subplatform_upload",
        "participant_selection",
        "ijro_report",
        "other",
    }
)


def parse(text: str) -> ParsedLine:
    return parse_line(text, today=TODAY, people=PEOPLE, type_codes=TYPE_CODES)


def test_tz7_example_type_due_and_assignee() -> None:
    """Пример из ТЗ 7: тип, срок и ответственный."""
    assert parse("к пятнице рассмотрение проекта постановления Минэкологии, Каримов") == (
        ParsedLine(
            title="Рассмотрение проекта постановления Минэкологии",
            type_code="review_and_endorse",
            due_on=date(2026, 10, 2),
            assignee_id="p-karimov",
            matched_type="рассмотр",
            matched_due="к пятнице",
            matched_assignee="Каримов",
        )
    )


@pytest.mark.parametrize(
    ("text", "due"),
    [
        ("сегодня справка по засухе", date(2026, 9, 25)),
        ("завтра выезд на полигон", date(2026, 9, 26)),
        ("послезавтра запрос в хокимият", date(2026, 9, 27)),
        ("через 3 дня согласование стандарта", date(2026, 9, 28)),
        ("через неделю отбор участников", date(2026, 10, 2)),
        ("через 2 недели ТЗ на группировку", date(2026, 10, 9)),
        ("до среды выгрузка в субплатформу", date(2026, 9, 30)),
        ("в понедельник справка", date(2026, 9, 28)),
        # Сказанное в пятницу «к концу недели» — сегодня.
        ("к концу недели справка", date(2026, 9, 25)),
        ("к концу месяца отчёт", date(2026, 9, 30)),
        ("к 15.10 сведения по поручению", date(2026, 10, 15)),
        ("до 3.03 план работ", date(2027, 3, 3)),
        ("к 15 октября сведения", date(2026, 10, 15)),
        ("10.01.2027 доклад", date(2027, 1, 10)),
    ],
)
def test_due(text: str, due: date) -> None:
    assert parse(text).due_on == due


@pytest.mark.parametrize(
    ("text", "assignee_id"),
    [
        ("поручить Каримову справку", "p-karimov"),
        ("справка — Юсуповой", "p-yusupova"),
        ("Юсупова Д. подготовит проект", "p-yusupova"),
        ("Рахимов Ш. выезд", "p-rakhimov"),
        ("отбор участников с Абдуллаевой", "p-abdullaeva"),
    ],
)
def test_assignee(text: str, assignee_id: str) -> None:
    assert parse(text).assignee_id == assignee_id


def test_assignee_leaves_title_with_initials() -> None:
    assert parse("Юсупова Д. подготовит проект соглашения").title == (
        "Подготовит проект соглашения"
    )


@pytest.mark.parametrize(
    ("text", "type_code"),
    [
        ("внести проект в Кабмин", "cabinet_submission"),
        ("согласовать и внести в Кабинет министров", "cabinet_submission"),
        ("подготовить ТЗ на платформу", "technical_spec"),
        ("визирование стандарта", "review_and_endorse"),
        ("согласование с Минфином", "approval"),
        ("аналитическая справка для АП", "analytical_note"),
        ("командировка в Навои", "site_visit"),
        ("опросник для хокимиятов", "request_or_survey"),
        ("выгрузка данных", "subplatform_upload"),
        ("отбор пилотных районов", "participant_selection"),
        ("сведения по поручению ПФ-155", "ijro_report"),
        ("позвонить в министерство", None),
    ],
)
def test_type(text: str, type_code: str | None) -> None:
    assert parse(text).type_code == type_code


def test_without_due_and_assignee_only_title() -> None:
    result = parse("  позвонить в министерство.  ")
    assert result.title == "Позвонить в министерство"
    assert result.due_on is None
    assert result.assignee_id is None


def test_nonexistent_date_is_not_due() -> None:
    assert parse("к 31.02 отчёт").due_on is None


# Сверх примеров экрана — случаи, которые сравнение с parse.ts на случайных строках
# показало спорными или которые экран не проверял.

NAMESAKES: list[tuple[object, str]] = [("p-karimov", "Каримов А."), ("p-karimova", "Каримова Л.")]


@pytest.mark.parametrize(
    ("text", "assignee_id"),
    [
        # «Каримову» — падеж обеих фамилий: выбор остаётся человеку.
        ("поручить Каримову справку", None),
        # Точное написание сильнее падежной формы.
        ("Каримова подготовит справку", "p-karimova"),
        ("Каримов подготовит справку", "p-karimov"),
    ],
)
def test_similar_surnames_are_never_guessed(text: str, assignee_id: str | None) -> None:
    result = parse_line(text, today=TODAY, people=NAMESAKES, type_codes=TYPE_CODES)
    assert result.assignee_id == assignee_id


@pytest.mark.parametrize(
    ("text", "today", "due"),
    [
        # В субботу конец недели — следующая пятница.
        ("к концу недели справка", date(2026, 9, 26), date(2026, 10, 2)),
        # Прошедшее 29.02 високосного года в следующем году не существует.
        ("к 29.02 отчёт", date(2028, 3, 10), None),
        # Год короче четырёх значащих цифр — опечатка; parse.ts его тоже не принимал.
        ("к 05.02.0001 отчёт", TODAY, None),
    ],
)
def test_due_edges(text: str, today: date, due: date | None) -> None:
    assert parse_line(text, today=today, people=PEOPLE, type_codes=TYPE_CODES).due_on == due


def test_extended_latin_initial_leaves_with_surname() -> None:
    result = parse("Каримов Ž. подготовит справку")
    assert result.matched_assignee == "Каримов Ž."
    assert result.title == "Подготовит справку"


def test_unknown_type_code_is_not_suggested() -> None:
    """Правило совпало, но такого типа нет в справочнике — предлагается следующий."""
    result = parse_line(
        "согласовать и внести в Кабмин", today=TODAY, people=PEOPLE, type_codes={"approval"}
    )
    assert (result.type_code, result.matched_type) == ("approval", "согласов")
