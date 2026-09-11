"""Чек-листы и теги задач (ORB-015).

Три критерия карточки и одно, что в ней не записано, но ломается тише всего: прогресс
чек-листа **вычисляется**, а не хранится. Хранимое число расходится с пунктами молча — и
на экране списка стоит «3 из 5» там, где пунктов четыре. Поэтому проверка ведётся не
чтением поля, а сверкой: после каждого изменения пунктов ответ обязан сойтись с тем, что
реально лежит в базе.

Про теги проверяется одно и то же с четырёх сторон: «ДЗЗ», «дзз», «ДЗЗ » и «ДЗЗ» с двойным
пробелом внутри — один тег. Развалится это правило — и вопрос «покажи всё по ДЗЗ» начнёт
возвращать треть, а понять, почему, будет нельзя: в словаре всё выглядит правильно.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.checklists import normalize_tag, progress
from app.domain.dictionaries import Priority, ProjectStatus
from app.repos.models import (
    AuditLog,
    Direction,
    Project,
    Tag,
    TaskChecklistItem,
    TaskTag,
)

pytestmark = pytest.mark.infra

API = "/api/v1"


async def a_task(api: AsyncClient, title: str = "Задача с чек-листом") -> str:
    response = await api.post(
        f"{API}/tasks", json={"title": title, "priority_code": Priority.NORMAL.value}
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def an_item(api: AsyncClient, task_id: str, text: str) -> str:
    response = await api.post(f"{API}/tasks/{task_id}/checklist", json={"text": text})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def a_project(session: AsyncSession, **overrides: Any) -> Project:
    direction = await session.scalar(select(Direction).limit(1))
    assert direction is not None

    fields: dict[str, Any] = {
        "code": f"PRJ-2026-{uuid.uuid4().int % 900 + 99:03d}",
        "title": "Проект",
        "kind": "project",
        "classification": "internal",
        "direction_id": direction.id,
        "status_code": ProjectStatus.IN_PROGRESS.value,
        "priority_code": Priority.NORMAL.value,
        "started_on": date(2026, 1, 1),
        "due_on": date(2026, 12, 31),
    }
    fields.update(overrides)

    project = Project(**fields)
    session.add(project)
    await session.flush()
    return project


class TestProgressIsComputed:
    """Прогресс считается из пунктов и нигде не лежит.

    Проверяется сверкой с базой, а не сравнением с ожидаемым числом: совпадение с
    константой переживёт появление хранимого счётчика, а расхождение с пунктами — нет.
    """

    @staticmethod
    async def actual(session: AsyncSession, task_id: str) -> tuple[int, int]:
        rows = list(
            await session.scalars(
                select(TaskChecklistItem.is_done).where(
                    TaskChecklistItem.task_id == uuid.UUID(task_id)
                )
            )
        )
        return sum(1 for done in rows if done), len(rows)

    @staticmethod
    async def reported(api: AsyncClient, task_id: str) -> tuple[int, int]:
        card = await api.get(f"{API}/tasks/{task_id}")
        assert card.status_code == 200, card.text
        return card.json()["checklist_done"], card.json()["checklist_total"]

    async def test_progress_follows_the_items_at_every_step(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        task = await a_task(assistant_api)
        assert await self.reported(assistant_api, task) == await self.actual(session, task)

        first = await an_item(assistant_api, task, "Согласовать смету")
        await an_item(assistant_api, task, "Подписать договор")
        assert await self.reported(assistant_api, task) == await self.actual(session, task)

        await assistant_api.patch(f"{API}/checklist-items/{first}", json={"is_done": True})
        assert await self.reported(assistant_api, task) == await self.actual(session, task)

        await assistant_api.delete(f"{API}/checklist-items/{first}")
        assert await self.reported(assistant_api, task) == await self.actual(session, task)

    async def test_no_checklist_is_not_zero_percent(self, assistant_api: AsyncClient) -> None:
        """Задача без чек-листа — не задача, в которой ничего не сделано.

        Ноль процентов на экране списка читается как тревога. Отсутствие чек-листа не
        сообщает ни о чём, и доля у такой задачи отсутствует, а не равна нулю.
        """
        task = await a_task(assistant_api)

        card = (await assistant_api.get(f"{API}/tasks/{task}")).json()

        assert card["checklist_total"] == 0
        assert card["checklist_percent"] is None

    async def test_an_untouched_checklist_is_zero_percent(self, assistant_api: AsyncClient) -> None:
        """А вот здесь ноль — правда: взялись и не сделали."""
        task = await a_task(assistant_api)
        await an_item(assistant_api, task, "Ещё не начато")

        card = (await assistant_api.get(f"{API}/tasks/{task}")).json()

        assert card["checklist_percent"] == 0

    async def test_progress_is_visible_in_the_task_list(self, assistant_api: AsyncClient) -> None:
        """Критерий: прогресс виден **в списке задач**, а не только в карточке."""
        task = await a_task(assistant_api, title="Со списком")
        done = await an_item(assistant_api, task, "Первое")
        await an_item(assistant_api, task, "Второе")
        await assistant_api.patch(f"{API}/checklist-items/{done}", json={"is_done": True})

        listed = (await assistant_api.get(f"{API}/tasks")).json()

        row = next(item for item in listed if item["id"] == task)
        assert (row["checklist_done"], row["checklist_total"]) == (1, 2)
        assert row["checklist_percent"] == 50

    async def test_the_list_asks_the_database_once_for_every_task(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Прогресс собирается одним запросом на весь список, а не запросом на строку.

        Запрос на строку не виден на пяти задачах и виден на пятистах: экран открывается
        секундами. Проверяется не время, а само обращение — одно на всю выборку.
        """
        for number in range(3):
            task = await a_task(assistant_api, title=f"Задача {number}")
            await an_item(assistant_api, task, "Пункт")

        statements: list[str] = []

        def record(conn: Any, cursor: Any, statement: str, *rest: Any) -> None:
            if "task_checklist_items" in statement and "SELECT" in statement:
                statements.append(statement)

        engine = session.get_bind()
        event.listen(engine, "before_cursor_execute", record)
        try:
            await assistant_api.get(f"{API}/tasks")
        finally:
            event.remove(engine, "before_cursor_execute", record)

        assert len(statements) == 1, f"обращений к пунктам: {len(statements)}, ожидалось одно"

    def test_the_percent_rounds_down(self) -> None:
        """«99 %» при одном невыполненном пункте из ста честнее, чем «100 %».

        Округление к ближайшему сделало бы последний пункт невидимым — а он и есть то,
        из-за чего дело не закончено.
        """
        assert progress(done=99, total=100).percent == 99
        assert progress(done=1, total=3).percent == 33
        assert progress(done=0, total=7).percent == 0
        assert progress(done=7, total=7).percent == 100

    def test_impossible_progress_is_refused(self) -> None:
        with pytest.raises(ValueError):
            progress(done=3, total=2)
        with pytest.raises(ValueError):
            progress(done=-1, total=2)


class TestChecklistItems:
    async def test_items_keep_the_order_they_were_given(self, assistant_api: AsyncClient) -> None:
        task = await a_task(assistant_api)
        first = await an_item(assistant_api, task, "Согласовать")
        second = await an_item(assistant_api, task, "Подписать")
        third = await an_item(assistant_api, task, "Отправить")

        listed = (await assistant_api.get(f"{API}/tasks/{task}/checklist")).json()
        assert [item["text"] for item in listed] == ["Согласовать", "Подписать", "Отправить"]

        reordered = await assistant_api.put(
            f"{API}/tasks/{task}/checklist/order", json={"item_ids": [third, first, second]}
        )

        assert reordered.status_code == 200, reordered.text
        after = (await assistant_api.get(f"{API}/tasks/{task}/checklist")).json()
        assert [item["text"] for item in after] == ["Отправить", "Согласовать", "Подписать"]

    async def test_a_stale_order_is_refused_not_applied_in_part(
        self, assistant_api: AsyncClient
    ) -> None:
        """Порядок, собранный до удаления пункта, применять нельзя.

        Частичное применение оставило бы часть пунктов с прежним порядком, и после
        перезагрузки чек-лист выглядел бы иначе, чем только что на экране.
        """
        task = await a_task(assistant_api)
        first = await an_item(assistant_api, task, "Первый")
        second = await an_item(assistant_api, task, "Второй")
        await an_item(assistant_api, task, "Третий")

        refused = await assistant_api.put(
            f"{API}/tasks/{task}/checklist/order", json={"item_ids": [second, first]}
        )

        assert refused.status_code == 422, refused.text
        after = (await assistant_api.get(f"{API}/tasks/{task}/checklist")).json()
        assert [item["text"] for item in after] == ["Первый", "Второй", "Третий"]

    async def test_a_checklist_of_a_missing_task_is_not_an_empty_list(
        self, assistant_api: AsyncClient
    ) -> None:
        """Пустой список означал бы «пунктов нет», и опечатка в адресе читалась бы как
        только что вычищенный кем-то чек-лист."""
        missing = await assistant_api.get(f"{API}/tasks/{uuid.uuid4()}/checklist")

        assert missing.status_code == 404

    async def test_deleting_the_task_takes_its_checklist(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Пункт без задачи не существует: он и есть её часть."""
        task = await a_task(assistant_api)
        await an_item(assistant_api, task, "Пункт")

        await assistant_api.delete(f"{API}/tasks/{task}")

        left = await session.scalar(
            select(func.count())
            .select_from(TaskChecklistItem)
            .where(TaskChecklistItem.task_id == uuid.UUID(task))
        )
        assert left == 0

    async def test_a_missing_item_is_not_found_not_a_crash(
        self, assistant_api: AsyncClient
    ) -> None:
        """Пункт, удалённый в другой вкладке, — это «не найдено», а не поломка."""
        gone = await assistant_api.patch(
            f"{API}/checklist-items/{uuid.uuid4()}", json={"is_done": True}
        )

        assert gone.status_code == 404

    async def test_a_list_matching_nothing_still_answers(self, assistant_api: AsyncClient) -> None:
        """Фильтр, под который не подошла ни одна задача, не должен ронять сбор прогресса.

        Пустой набор идентификаторов — вырожденный случай, до которого обычные проверки
        не доходят: в них всегда есть хоть одна задача.
        """
        empty = await assistant_api.get(f"{API}/tasks", params={"search": "такого нет нигде"})

        assert empty.status_code == 200
        assert empty.json() == []

    async def test_the_leader_reads_but_does_not_tick(
        self, leader_api: AsyncClient, assistant_api: AsyncClient
    ) -> None:
        """Руководитель видит всё и не меняет ничего (ADR-0011).

        Отказ — 403, а не 401: сессия у него действует, и уводить его на экран входа за
        попытку отметить пункт нельзя.
        """
        task = await a_task(assistant_api)
        item = await an_item(assistant_api, task, "Пункт")

        assert (await leader_api.get(f"{API}/tasks/{task}/checklist")).status_code == 200

        refused = await leader_api.patch(f"{API}/checklist-items/{item}", json={"is_done": True})
        assert refused.status_code == 403


class TestTagsAreReused:
    """Критерий: ввод существующего тега не создаёт дубликат."""

    @staticmethod
    async def count_of(session: AsyncSession) -> int:
        total = await session.scalar(select(func.count()).select_from(Tag))
        return int(total or 0)

    @pytest.mark.parametrize(
        ("second", "why"),
        [
            ("ДЗЗ", "то же написание"),
            ("дзз", "другой регистр"),
            ("  ДЗЗ  ", "пробелы по краям"),
            ("ДЗЗ", "повтор в том же наборе"),
        ],
    )
    async def test_the_same_tag_is_not_created_twice(
        self, assistant_api: AsyncClient, session: AsyncSession, second: str, why: str
    ) -> None:
        first_task = await a_task(assistant_api, title="Первая")
        second_task = await a_task(assistant_api, title="Вторая")

        await assistant_api.put(f"{API}/tasks/{first_task}/tags", json={"names": ["ДЗЗ"]})
        before = await self.count_of(session)

        await assistant_api.put(f"{API}/tasks/{second_task}/tags", json={"names": [second]})

        assert await self.count_of(session) == before, f"дубликат тега: {why}"

    async def test_an_existing_tag_keeps_its_own_spelling(self, assistant_api: AsyncClient) -> None:
        """Написание принадлежит тегу, а не последнему, кто его набрал.

        Переписать написание значило бы поменять его у всех уже помеченных задач из-за
        одного ввода в одной карточке.
        """
        first_task = await a_task(assistant_api, title="Первая")
        second_task = await a_task(assistant_api, title="Вторая")
        await assistant_api.put(f"{API}/tasks/{first_task}/tags", json={"names": ["ДЗЗ"]})

        applied = await assistant_api.put(
            f"{API}/tasks/{second_task}/tags", json={"names": ["дзз"]}
        )

        assert [tag["name"] for tag in applied.json()] == ["ДЗЗ"]
        listed = (await assistant_api.get(f"{API}/tags")).json()
        assert [tag["name"] for tag in listed] == ["ДЗЗ"]

    async def test_inner_double_spaces_are_the_same_tag(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """«ДЗЗ  Ташкент» и «ДЗЗ Ташкент» на экране неразличимы, значит это один тег."""
        task = await a_task(assistant_api)

        await assistant_api.put(f"{API}/tasks/{task}/tags", json={"names": ["ДЗЗ Ташкент"]})
        await assistant_api.put(f"{API}/tasks/{task}/tags", json={"names": ["ДЗЗ  Ташкент"]})

        assert await self.count_of(session) == 1

    async def test_setting_tags_replaces_the_whole_set(self, assistant_api: AsyncClient) -> None:
        task = await a_task(assistant_api)
        await assistant_api.put(f"{API}/tasks/{task}/tags", json={"names": ["ДЗЗ", "Срочно"]})

        await assistant_api.put(f"{API}/tasks/{task}/tags", json={"names": ["Срочно"]})

        listed = (await assistant_api.get(f"{API}/tasks/{task}/tags")).json()
        assert [tag["name"] for tag in listed] == ["Срочно"]

    async def test_removing_a_tag_from_a_task_keeps_it_in_the_dictionary(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Словарь не пустеет от того, что тег сняли с одной задачи.

        Иначе набранное однажды слово приходилось бы набирать заново — а теги и заводятся
        ради того, чтобы одинаково называть похожее.
        """
        task = await a_task(assistant_api)
        await assistant_api.put(f"{API}/tasks/{task}/tags", json={"names": ["ДЗЗ"]})

        await assistant_api.put(f"{API}/tasks/{task}/tags", json={"names": []})

        assert await self.count_of(session) == 1
        assert (await assistant_api.get(f"{API}/tasks/{task}/tags")).json() == []

    async def test_deleting_the_task_takes_its_marks_not_the_tags(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        task = await a_task(assistant_api)
        await assistant_api.put(f"{API}/tasks/{task}/tags", json={"names": ["ДЗЗ"]})

        await assistant_api.delete(f"{API}/tasks/{task}")

        marks = await session.scalar(select(func.count()).select_from(TaskTag))
        assert marks == 0
        assert await self.count_of(session) == 1

    async def test_an_empty_tag_is_refused_with_words(self, assistant_api: AsyncClient) -> None:
        refused = await assistant_api.put(
            f"{API}/tasks/{await a_task(assistant_api)}/tags", json={"names": ["   "]}
        )

        assert refused.status_code == 422, refused.text

    def test_normalization_keeps_the_case_it_was_given(self) -> None:
        """Приведение к нижнему регистру здесь навсегда сделало бы «ДЗЗ» тегом «дзз»."""
        assert normalize_tag("  ДЗЗ  Ташкент ") == "ДЗЗ Ташкент"
        assert normalize_tag("ДЗЗ") == "ДЗЗ"

        with pytest.raises(ValueError):
            normalize_tag("   ")
        with pytest.raises(ValueError):
            normalize_tag("т" * 51)


class TestChecklistInTheFile:
    async def test_the_export_carries_the_checklist_too(self, assistant_api: AsyncClient) -> None:
        """Файл обещает быть той же выборкой, что на экране.

        Появилась колонка на экране — появилась и в файле, иначе обещание перестаёт
        выполняться, и заметить это можно только сличая их вручную.
        """
        task = await a_task(assistant_api, title="С чек-листом")
        done = await an_item(assistant_api, task, "Первое")
        await an_item(assistant_api, task, "Второе")
        await assistant_api.patch(f"{API}/checklist-items/{done}", json={"is_done": True})

        exported = await assistant_api.get(f"{API}/tasks/export.csv")

        text = exported.content.decode("utf-8-sig")
        assert "Чек-лист" in text.splitlines()[0]
        line = next(row for row in text.splitlines() if "С чек-листом" in row)
        assert "1 из 2" in line

    async def test_a_task_without_a_checklist_leaves_the_cell_empty(
        self, assistant_api: AsyncClient
    ) -> None:
        """«0 из 0» в сотне строк — шум, по которому нельзя отсортировать."""
        await a_task(assistant_api, title="Без чек-листа")

        exported = await assistant_api.get(f"{API}/tasks/export.csv")

        line = next(
            row
            for row in exported.content.decode("utf-8-sig").splitlines()
            if "Без чек-листа" in row
        )
        assert "0 из 0" not in line

    async def test_a_checklist_of_a_classified_project_does_not_leave_either(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Гриф закрывает задачу целиком, вместе с её чек-листом (ADR-0007).

        Проверка стоит в функции выдачи, и колонка чек-листа ничего в ней не меняет — но
        убедиться в этом надо: новая колонка собирается отдельным запросом, и он мог бы
        обойти проверку своим путём.
        """
        closed = await a_project(session, classification="restricted", title="Закрытый")
        created = await assistant_api.post(
            f"{API}/tasks",
            json={
                "title": "Закрытая задача",
                "project_id": str(closed.id),
                "priority_code": Priority.NORMAL.value,
            },
        )
        task = str(created.json()["id"])
        await an_item(assistant_api, task, "Секретный пункт")

        exported = await assistant_api.get(f"{API}/tasks/export.csv")

        text = exported.content.decode("utf-8-sig")
        assert "Закрытая задача" not in text
        assert "Секретный пункт" not in text


class TestEveryChangeIsInTheJournal:
    async def test_ticking_an_item_is_recorded(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """«Кто отметил пункт выполненным» — тот же вопрос, что «кто поменял статус».

        По поручению он задаётся всерьёз, и инвариант 4 из CLAUDE.md требует ответа.
        """
        task = await a_task(assistant_api)
        item = await an_item(assistant_api, task, "Пункт")

        await assistant_api.patch(f"{API}/checklist-items/{item}", json={"is_done": True})

        entries = list(
            await session.scalars(select(AuditLog).where(AuditLog.entity_id == uuid.UUID(item)))
        )
        assert entries, "отметка пункта не попала в журнал изменений"
        assert any(entry.action == "updated" for entry in entries)
