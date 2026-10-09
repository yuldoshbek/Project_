"""Поиск по всем разделам (ТЗ 6, V19): правило строки и один запрос на все виды.

Главные обещания:

1. находится проект, задача, поручение, письмо, организация, идея, мероприятие — по
   части названия или номера, без учёта регистра;
2. содержание поручения на узбекской кириллице находится запросом латиницей;
3. запрос короче двух знаков не ищется, а знаки `%` и `_` ищутся буквально.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clock import now_utc
from app.domain.dictionaries import OrganizationKind
from app.domain.ijro import IjroSource
from app.domain.interaction import Direction
from app.domain.preparations import PreparationKind
from app.domain.search import MIN_LENGTH, PER_KIND, like_pattern, normalize, spellings
from app.repos.models import (
    Idea,
    IjroAssignment,
    IjroDocument,
    Letter,
    Organization,
    Preparation,
    User,
)
from tests.factories import make_project, make_task

SEARCH = "/api/v1/search"


class TestSpellings:
    def test_latin_query_is_also_searched_in_cyrillic(self) -> None:
        """Помощник набирает латиницей — поручение хранится кириллицей."""
        assert spellings("Kosmik") == ("kosmik", "космик")

    def test_uzbek_digraphs_and_apostrophes(self) -> None:
        assert spellings("Oʻzbekiston")[1] == "ўзбекистон"
        assert spellings("shahar")[1] == "шаҳар"

    def test_cyrillic_query_is_also_searched_in_latin(self) -> None:
        assert spellings("ПФ-155") == ("пф-155", "pf-155")

    def test_digits_are_one_spelling(self) -> None:
        assert spellings(" 155 ") == ("155",)

    def test_too_short_is_not_searched(self) -> None:
        assert spellings("а" * (MIN_LENGTH - 1)) == ()
        assert spellings("   ") == ()

    def test_normalize_folds_spaces_and_apostrophes(self) -> None:
        assert normalize("  Oʻz   bek ") == "o'z bek"

    def test_like_wildcards_are_literal(self) -> None:
        backslash = chr(92)
        assert like_pattern("50%_a") == f"%50{backslash}%{backslash}_a%"


async def _organization(session: AsyncSession, name: str) -> Organization:
    organization = Organization(name=name, kind=OrganizationKind.MINISTRY.value)
    session.add(organization)
    await session.flush()
    return organization


async def _assignment(session: AsyncSession, content: str, number: str) -> IjroAssignment:
    document = IjroDocument(
        code_norm=f"{number}-{uuid.uuid4().hex[:8]}",
        kind="farmon",
        number_raw=number,
        issued_on=date(2026, 3, 1),
        source=IjroSource.LEGAL.value,
    )
    session.add(document)
    await session.flush()
    assignment = IjroAssignment(
        code=f"IJR-2026-{uuid.uuid4().hex[:6]}",
        document_id=document.id,
        due_on=date(2026, 12, 1),
        content=content,
    )
    session.add(assignment)
    await session.flush()
    return assignment


def _group(body: dict[str, list[dict[str, object]]], kind: str) -> dict[str, object] | None:
    return next((group for group in body["groups"] if group["kind"] == kind), None)


def _found(body: dict[str, list[dict[str, object]]], kind: str) -> list[object]:
    group = _group(body, kind)
    if group is None:
        return []
    hits = group["hits"]
    assert isinstance(hits, list)
    return [hit["title"] for hit in hits]


@pytest.mark.infra
class TestSearchApi:
    async def test_every_kind_by_part_of_title(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Одно слово без учёта регистра — находки всех видов, каждая в своей группе."""
        today = now_utc().date()
        project = await make_project(
            session, due_on=today + timedelta(days=90), title="Геопортал агентства"
        )
        await make_task(session, due_at=None, project=project, title="Выгрузка в геопортал")
        await _assignment(session, "Геопортал маълумотларини янгилаш", "ПФ-155")
        ministry = await _organization(session, "Геопортал Минэкологии")
        session.add(
            Letter(
                direction=Direction.OUTGOING.value,
                organization_id=ministry.id,
                subject="О доступе к геопорталу",
                number="01-17/905",
                sent_on=today,
            )
        )
        author = await session.scalar(select(User.id).limit(1))
        assert author is not None
        session.add(Idea(text="Геопортал для регионов", author_id=author))
        session.add(
            Preparation(
                kind=PreparationKind.EVENT.value,
                title="Презентация геопортала",
                show_on=today + timedelta(days=10),
            )
        )
        await session.flush()

        body = (await leader_api.get(SEARCH, params={"q": "ГЕОПОРТАЛ"})).json()

        assert _found(body, "project") == ["Геопортал агентства"]
        assert _found(body, "task") == ["Выгрузка в геопортал"]
        assert _found(body, "ijro") == ["Геопортал маълумотларини янгилаш"]
        assert _found(body, "letter") == ["О доступе к геопорталу"]
        assert _found(body, "organization") == ["Геопортал Минэкологии"]
        assert _found(body, "idea") == ["Геопортал для регионов"]
        assert _found(body, "preparation") == ["Презентация геопортала"]
        task = _group(body, "task")
        assert task is not None
        assert task["hits"][0]["context"] == "Геопортал агентства"  # type: ignore[index]

    async def test_cyrillic_assignment_by_latin_query(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        await _assignment(session, "Космик мониторинг маълумотлари асосида", "ПҚ-312")

        body = (await leader_api.get(SEARCH, params={"q": "kosmik"})).json()

        assert _found(body, "ijro") == ["Космик мониторинг маълумотлари асосида"]
        ijro = _group(body, "ijro")
        assert ijro is not None
        assert ijro["hits"][0]["context"] == "ПҚ-312"  # type: ignore[index]

    async def test_whole_number_comes_first(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        today = now_utc().date()
        exact = await make_project(session, due_on=today + timedelta(days=30), title="Первый")
        await make_project(session, due_on=today + timedelta(days=30), title=f"Про {exact.code}")

        body = (await leader_api.get(SEARCH, params={"q": exact.code.lower()})).json()

        project = _group(body, "project")
        assert project is not None
        assert project["hits"][0]["id"] == str(exact.id)  # type: ignore[index]

    async def test_more_than_a_group_holds(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        today = now_utc().date()
        for number in range(PER_KIND + 1):
            await make_project(
                session, due_on=today + timedelta(days=30), title=f"Спутник {number}"
            )

        body = (await leader_api.get(SEARCH, params={"q": "спутник"})).json()

        project = _group(body, "project")
        assert project is not None
        assert len(project["hits"]) == PER_KIND  # type: ignore[arg-type]
        assert project["more"] is True

    async def test_short_query_is_empty_not_an_error(self, leader_api: AsyncClient) -> None:
        response = await leader_api.get(SEARCH, params={"q": "г"})
        assert response.status_code == 200
        assert response.json()["groups"] == []

    async def test_wildcards_match_literally(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        today = now_utc().date()
        await make_project(session, due_on=today + timedelta(days=30), title="Скидка 50% на канал")
        await make_project(session, due_on=today + timedelta(days=30), title="Канал 500 Мбит")

        body = (await leader_api.get(SEARCH, params={"q": "50%"})).json()

        assert _found(body, "project") == ["Скидка 50% на канал"]
