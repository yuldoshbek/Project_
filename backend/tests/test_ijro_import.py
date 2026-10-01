"""Привоз таблицы «Ижро» — обещания вкладки «Загрузка» (ТЗ 7, экран утверждён 30.09.2026).

1. **Разбор**: ячейка — абзацы, разделитель месяца, год из заголовка, механизм отдельно.
2. **Шапка без обязательной графы — отказ**, а не сдвиг колонок; не `.docx` — отказ.
3. **Семь классов** предпросмотра; плохая строка не останавливает привоз.
4. **Перенос срока записывается только подтверждённый** и попадает в историю продлений.
5. **Привоз меняет только поля источника** (инвариант 4): этап и проблема остаются.
6. **Та же таблица второй раз ничего не меняет.**
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import docx
from app.domain.errors import RuleViolationError
from app.domain.ijro import DueYearSource, band_sort_key, normalize_document_code
from app.domain.ijro_import import parse_table
from app.repos.models import (
    IjroAssignment,
    IjroDocument,
    IjroExtension,
    IjroPersonAlias,
    Organization,
)
from tests.docx_builder import build, row
from tests.factories import make_person

YEAR = 2027
TITLE = f"1. ПА Назорат жадвали {YEAR} йил"
DOCUMENT = ("Фармон", "ПФ-777-сон", "14.10.2026 й")
IMPORTS = "/api/v1/ijro/imports"


def parsed(content: bytes) -> Any:
    document = docx.read(content)
    return parse_table(
        document.paragraphs,
        [[each.cells for each in table] for table in document.tables],
        fallback_year=2000,
    )


class TestReading:
    def test_cells_keep_paragraphs_and_the_month_separator_sets_the_block(self) -> None:
        table = parsed(
            build(
                TITLE,
                [
                    "СЕНТЯБРЬ",
                    row(
                        1,
                        DOCUMENT,
                        [
                            "1-банд. Дастур ишлаб чиқилсин.",
                            "Амалга ошириш механизми:",
                            "Вазирликлар билан келишилади.",
                        ],
                        "25 август",
                        ["А.Шакиров", "Асосий ижрочи:", "Сув хўжалиги вазирлиги"],
                    ),
                ],
            )
        )
        (line,) = table.rows
        assert table.table_year == YEAR
        assert line.document_code == "ПФ-777"
        assert line.issued_on == date(2026, 10, 14)
        assert line.band == "1-банд"
        assert line.content == "1-банд. Дастур ишлаб чиқилсин."
        assert line.mechanism == "Вазирликлар билан келишилади."
        # «25 август» под «СЕНТЯБРЬ» — перенесённая просрочка того же года (ADR-0025).
        assert (line.due_on, line.due_year_source) == (date(YEAR, 8, 25), DueYearSource.FROM_BLOCK)
        assert (line.responsible_ours, line.lead_raw) == ("А.Шакиров", "Сув хўжалиги вазирлиги")
        assert line.block_label == "СЕНТЯБРЬ"

    def test_a_bad_row_is_reported_and_the_rest_goes_on(self) -> None:
        table = parsed(
            build(
                TITLE,
                [
                    row(1, DOCUMENT, ["1-банд. Биринчи."], "15 июнь", ["Каримов А."]),
                    row(2, DOCUMENT, ["2-банд. Иккинчи."], "қачондир", ["Каримов А."]),
                    row(3, DOCUMENT, ["3-банд. Учинчи."], "10 июль", []),
                ],
            )
        )
        assert [line.band for line in table.rows] == ["1-банд"]
        assert [(bad.index, bad.reason) for bad in table.bad] == [
            (2, "due-unparsed"),
            (3, "responsible-empty"),
        ]

    def test_a_table_without_a_required_column_is_refused(self) -> None:
        content = build(TITLE, [], header=("№", "Ҳужжат", "Мазмуни", "Масъул"))
        with pytest.raises(RuleViolationError, match="шапка"):
            parsed(content)

    def test_not_a_docx_is_refused(self) -> None:
        with pytest.raises(RuleViolationError, match="Word"):
            docx.read(b"PK\x03\x04 not really a zip")

    def test_entity_declarations_are_refused(self) -> None:
        xml = '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>'
        with pytest.raises(RuleViolationError):
            docx.read(build(TITLE, [], raw_xml=xml))


# ---------------------------------------------------------------------------
# Предпросмотр и применение через API
# ---------------------------------------------------------------------------


async def registry(session: AsyncSession) -> dict[str, IjroAssignment]:
    """Четыре поручения ПФ-777 в реестре — как после прошлого привоза."""
    karimov = await make_person(session, "Каримов А.")
    session.add(IjroPersonAlias(alias_norm="каримов а.", person_id=karimov.id, source="manual"))
    document = IjroDocument(
        code_norm=normalize_document_code(" ".join(DOCUMENT)),
        kind="farmon",
        number_raw="ПФ-777",
        issued_on=date(2026, 10, 14),
        source="pa",
        title_raw="\n".join(DOCUMENT),
    )
    session.add(document)
    await session.flush()
    specs = {
        "first": ("1-банд", "1-банд. Биринчи топшириқ бажарилсин.", date(YEAR, 6, 15)),
        "second": ("2-банд", "2-банд. Иккинчи топшириқ.", date(YEAR, 7, 20)),
        "third": ("3-банд", "3-банд. Учинчи топшириқ.", date(YEAR, 8, 25)),
        "fourth": ("4-банд", "4-банд. Тўртинчи топшириқ.", date(YEAR, 9, 10)),
    }
    found = {}
    for number, (key, (band, content, due)) in enumerate(specs.items(), start=1):
        found[key] = IjroAssignment(
            code=f"IJR-{YEAR}-{number:03d}",
            document_id=document.id,
            band=band,
            band_sort=band_sort_key(band),
            content=content,
            due_on=due,
            original_due_on=due,
            responsible_raw="Каримов А.",
            responsible_person_id=karimov.id,
        )
    session.add_all(found.values())
    await session.flush()
    return found


def table() -> bytes:
    return build(
        TITLE,
        [
            row(1, DOCUMENT, ["1-банд. Биринчи топшириқ бажарилсин."], "15 июнь", ["Каримов А."]),
            row(
                2,
                DOCUMENT,
                ["2-банд. Иккинчи топшириқ, аниқлаштирилган."],
                "20 июль",
                ["Каримов А."],
            ),
            row(3, DOCUMENT, ["3-банд. Учинчи топшириқ."], "25 сентябрь", ["Каримов А."]),
            row(
                4,
                DOCUMENT,
                ["5-банд. Бешинчи топшириқ."],
                "10 октябрь",
                ["Ш.Арибжанов Асосий ижрочи:", "Сув хўжалиги вазирлиги"],
            ),
            row(5, DOCUMENT, ["6-банд. Олтинчи."], "қачондир", ["Каримов А."]),
        ],
    )


async def upload(api: AsyncClient, content: bytes) -> Any:
    return await api.post(
        IMPORTS,
        params={"file": "ПА Назорат жадвали.docx", "source": "pa"},
        content=content,
        headers={"Content-Type": docx_type()},
    )


def docx_type() -> str:
    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def by_class(preview: dict[str, Any], name: str) -> list[dict[str, Any]]:
    return [each for each in preview["rows"] if each["class"] == name]


@pytest.mark.infra
class TestPreviewAndApply:
    async def test_the_seven_classes(
        self, session: AsyncSession, assistant_api: AsyncClient
    ) -> None:
        await registry(session)
        response = await upload(assistant_api, table())
        assert response.status_code == 201, response.text
        preview = response.json()

        assert preview["table_year"] == YEAR
        assert preview["counts"] == {
            "new": 1,
            "unchanged": 1,
            "text_changed": 1,
            "responsible_changed": 0,
            "due_moved": 1,
            "vanished": 1,
            "unrecognized": 1,
        }
        (moved,) = by_class(preview, "due_moved")
        assert moved["due_move"] == {
            "from": f"{YEAR}-08-25",
            "to": f"{YEAR}-09-25",
            "suggested_kind": "extension",
        }
        (changed,) = by_class(preview, "text_changed")
        assert changed["diff"]["field"] == "content"
        (new,) = by_class(preview, "new")
        # «Ш.Арибжанов» — не «Каримов А.»: склеивать написания система не берётся (CLAUDE.md).
        assert new["unmatched"] == {"raw": "Ш.Арибжанов", "suggestions": []}
        (bad,) = by_class(preview, "unrecognized")
        assert bad["raw"].startswith("5")

    async def test_the_leader_does_not_upload(self, leader_api: AsyncClient) -> None:
        response = await upload(leader_api, table())
        assert response.status_code == 403

    async def test_apply_writes_only_source_fields_and_confirmed_moves(
        self, session: AsyncSession, assistant_api: AsyncClient
    ) -> None:
        found = await registry(session)
        second = found["second"]
        # Наши поля до привоза: этап и проблема. Привоз не трогает их никогда (инвариант 4).
        stage = await assistant_api.put(
            f"/api/v1/ijro/assignments/{second.id}/stage",
            json={"stage": "in_progress", "version": second.version},
        )
        assert stage.status_code == 204
        problem = await assistant_api.put(
            f"/api/v1/ijro/assignments/{second.id}/problem",
            json={"problem": "Маълумот келмади", "proposal": None, "version": second.version + 1},
        )
        assert problem.status_code == 204

        preview = (await upload(assistant_api, table())).json()
        (moved,) = by_class(preview, "due_moved")
        (vanished,) = by_class(preview, "vanished")
        (new,) = by_class(preview, "new")
        arib = await make_person(session, "Арибжанов Ш.")

        response = await assistant_api.post(
            f"{IMPORTS}/{preview['batch_id']}/apply",
            json={
                "due_moves": {moved["id"]: "extension"},
                "aliases": {new["id"]: str(arib.id)},
                "removed": [vanished["id"]],
            },
        )
        assert response.status_code == 200, response.text
        assert response.json() == {
            "outcome": "applied",
            "created": 1,
            "changed": 2,
            "vanished": 1,
            "removed": 1,
            "extensions": 1,
            "pending_extensions": 0,
        }

        await session.refresh(second)
        assert second.content == "2-банд. Иккинчи топшириқ, аниқлаштирилган."
        assert (second.state, second.problem) == ("in_progress", "Маълумот келмади")

        third = found["third"]
        await session.refresh(third)
        assert (third.original_due_on, third.due_on) == (date(YEAR, 8, 25), date(YEAR, 9, 25))
        extension = await session.scalar(
            select(IjroExtension).where(IjroExtension.assignment_id == third.id)
        )
        assert extension is not None
        assert (extension.due_from, extension.due_to, extension.kind) == (
            date(YEAR, 8, 25),
            date(YEAR, 9, 25),
            "extension",
        )

        await session.refresh(found["fourth"])
        assert found["fourth"].state == "removed_from_control"

        created = await session.scalar(
            select(IjroAssignment).where(IjroAssignment.band == "5-банд")
        )
        assert created is not None
        assert created.responsible_person_id == arib.id
        assert created.is_co_executor
        lead = await session.get(Organization, created.lead_organization_id)
        assert lead is not None
        assert (lead.name, lead.kind) == ("Сув хўжалиги вазирлиги", "ministry")
        assert created.code.startswith("IJR-")

        view = (await assistant_api.get("/api/v1/ijro")).json()
        last = next(each for each in view["questions"] if each["key"] == "last_batch")
        assert (last["created"], last["changed"], last["vanished"]) == (1, 2, 1)
        assert view["batches"][0]["file"] == "ПА Назорат жадвали.docx"

    async def test_an_unconfirmed_move_waits(
        self, session: AsyncSession, assistant_api: AsyncClient
    ) -> None:
        found = await registry(session)
        preview = (await upload(assistant_api, table())).json()
        response = await assistant_api.post(f"{IMPORTS}/{preview['batch_id']}/apply", json={})

        assert response.json()["pending_extensions"] == 1
        assert response.json()["extensions"] == 0
        await session.refresh(found["third"])
        assert found["third"].due_on == date(YEAR, 8, 25)
        last = next(
            each
            for each in (await assistant_api.get("/api/v1/ijro")).json()["questions"]
            if each["key"] == "last_batch"
        )
        assert last["pending_extensions"] == 1

    async def test_the_same_table_twice_changes_nothing(
        self, session: AsyncSession, assistant_api: AsyncClient
    ) -> None:
        await registry(session)
        content = table()
        first = (await upload(assistant_api, content)).json()
        applied = await assistant_api.post(f"{IMPORTS}/{first['batch_id']}/apply", json={})
        assert applied.json()["outcome"] == "applied"
        count = len(list(await session.scalars(select(IjroAssignment.id))))

        again = (await upload(assistant_api, content)).json()
        assert again["already_applied_on"] is not None
        assert again["rows"] == []
        repeat = await assistant_api.post(f"{IMPORTS}/{again['batch_id']}/apply", json={})
        assert repeat.json()["outcome"] == "already_applied"
        assert len(list(await session.scalars(select(IjroAssignment.id)))) == count

    async def test_a_foreign_file_is_refused_with_a_message(
        self, assistant_api: AsyncClient
    ) -> None:
        response = await upload(assistant_api, b"plain text, not a table")
        assert response.status_code == 422
        assert "Word" in response.json()["title"] or "Word" in response.text

    async def test_unknown_batch_is_not_found(self, assistant_api: AsyncClient) -> None:
        response = await assistant_api.post(f"{IMPORTS}/{uuid.uuid4()}/apply", json={})
        assert response.status_code == 404
