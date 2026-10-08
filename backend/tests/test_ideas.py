"""Идеи и карты — путь идеи до проекта одним действием, общая карта (ТЗ 3.6, 5, 11).

1. **«Что ждёт моего „да“?»** — идеи на рассмотрении, дольше всех ждущая первой (V46).
2. **Решение руководителя** заводит проект или задачу и ссылку на них в одной транзакции;
   помощник не решает; правка по устаревшей версии — честный отказ.
3. **Идея из Захвата** — сразу набросок раздела.
4. **Карта**: ступень связанного узла — та же, что на Пульте; кольцо родителей запрещено;
   узел уходит с ветвью; узел превращается в задачу одним действием.
"""

from __future__ import annotations

import uuid
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import demo
from app.domain.audit import AuditAction
from app.domain.clock import now_utc
from app.domain.errors import RuleViolationError
from app.domain.ideas import awaiting, branch_stamp, check_parent, subtree
from app.repos.models import AuditLog, MapNode, Project, Task

TASHKENT = ZoneInfo("Asia/Tashkent")
IDEAS = "/api/v1/ideas"
MAPS = "/api/v1/maps"


@pytest.fixture
async def loaded(session: AsyncSession) -> None:
    now = now_utc()
    await demo.before_visit(session, now=now, zone=TASHKENT)
    await demo.after_visit(session, now=now, zone=TASHKENT)


def by_text(items: list[dict[str, Any]], start: str) -> dict[str, Any]:
    return next(each for each in items if each["text"].startswith(start))


async def decisions_in_journal(session: AsyncSession, idea_id: str) -> list[dict[str, Any]]:
    """Записи журнала о решении по идее — правки, которые перевели её в «решено»."""
    changes = await session.scalars(
        select(AuditLog.changes).where(
            AuditLog.entity_type == "ideas",
            AuditLog.entity_id == uuid.UUID(idea_id),
            AuditLog.action == AuditAction.UPDATED.value,
        )
    )
    return [each for each in changes if each.get("step", {}).get("to") == "decided"]


async def map_id(api: AsyncClient, title: str) -> str:
    body = (await api.get(IDEAS)).json()
    found: str = next(each["id"] for each in body["maps"] if each["title"] == title)
    return found


@pytest.mark.infra
@pytest.mark.usefixtures("loaded")
class TestIdeas:
    async def test_awaiting_answers_with_the_oldest(self, leader_api: AsyncClient) -> None:
        body = (await leader_api.get(IDEAS)).json()
        (answer,) = body["questions"]
        assert (answer["key"], answer["count"], answer["oldest_days"]) == ("awaiting", 2, 9)
        catalogue = by_text(body["items"], "Открытый каталог снимков")
        water = by_text(body["items"], "Ежемесячная сводка")
        assert answer["rows"] == [catalogue["id"], water["id"]]
        assert answer["oldest_id"] == catalogue["id"]
        assert (catalogue["waiting_days"], water["waiting_days"]) == (9, 3)

        decided = by_text(body["items"], "Пилот мониторинга посевов")
        assert (decided["outcome"], decided["link"]["type"]) == ("project", "project")
        assert decided["link"]["title"] == "Пилот: мониторинг посевов"
        draft = by_text(body["items"], "Спутниковый мониторинг пастбищ")
        assert (draft["step"], draft["author"], draft["waiting_days"]) == ("draft", "leader", 0)

        maps = {
            each["title"]: (each["mode"], each["nodes"], each["linked"]) for each in body["maps"]
        }
        assert maps == {
            "Мониторинг сельского хозяйства": ("structure", 8, 4),
            "Космическое образование": ("sketch", 4, 0),
        }
        assert body["project_types"]

    async def test_leader_turns_an_idea_into_a_project(
        self, leader_api: AsyncClient, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        body = (await leader_api.get(IDEAS)).json()
        idea = by_text(body["items"], "Открытый каталог снимков")
        path = f"{IDEAS}/{idea['id']}/decision"
        decision = {"outcome": "project", "type_code": "industry_pilot", "version": idea["version"]}
        # Демо-данные уже оставили в журнале запись «создана»: решение ищется по содержимому,
        # иначе проверка проходила бы и без записи о нём.
        assert await decisions_in_journal(session, idea["id"]) == []

        assert (await assistant_api.post(path, json=decision)).status_code == 403
        no_type = {**decision, "type_code": None}
        assert (await leader_api.post(path, json=no_type)).status_code == 422
        stale = {**decision, "version": idea["version"] + 1}
        assert (await leader_api.post(path, json=stale)).status_code == 409

        response = await leader_api.post(path, json=decision)
        assert response.status_code == 200, response.text
        created = response.json()["created_id"]
        project = await session.get(Project, uuid.UUID(created))
        assert project is not None and project.title == idea["text"]

        after = by_text((await leader_api.get(IDEAS)).json()["items"], "Открытый каталог снимков")
        assert (after["step"], after["outcome"]) == ("decided", "project")
        assert after["link"]["id"] == created
        (journal,) = await decisions_in_journal(session, idea["id"])
        assert journal["step"] == {"from": "review", "to": "decided"}
        assert journal["outcome"] == {"from": None, "to": "project"}
        assert journal["project_id"] == {"from": None, "to": created}
        # Решённую в проект не отправить на рассмотрение снова.
        again = await leader_api.put(
            f"{IDEAS}/{idea['id']}/review", json={"version": after["version"]}
        )
        assert again.status_code == 422

    async def test_task_and_postponed_and_back_to_review(
        self, leader_api: AsyncClient, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        body = (await leader_api.get(IDEAS)).json()
        water = by_text(body["items"], "Ежемесячная сводка")
        made = await leader_api.post(
            f"{IDEAS}/{water['id']}/decision",
            json={"outcome": "task", "version": water["version"]},
        )
        task = await session.get(Task, uuid.UUID(made.json()["created_id"]))
        assert task is not None and task.title.startswith("Ежемесячная сводка")

        postponed = by_text(body["items"], "Мобильное приложение")
        # Отложенная — не тупик (V47): помощник отправляет её снова.
        sent = await assistant_api.put(
            f"{IDEAS}/{postponed['id']}/review", json={"version": postponed["version"]}
        )
        assert sent.status_code == 204
        answer = (await leader_api.get(IDEAS)).json()["questions"][0]
        assert answer["rows"][-1] == postponed["id"]

    async def test_idea_from_capture_is_a_draft(self, leader_api: AsyncClient) -> None:
        text = "Снимки для учебников географии"
        saved = await leader_api.post("/api/v1/captures", json={"kind": "idea", "text": text})
        assert saved.status_code == 201, saved.text
        found = by_text((await leader_api.get(IDEAS)).json()["items"], text)
        assert (found["step"], found["author"]) == ("draft", "leader")

    async def test_both_write_and_edit_by_version(
        self, leader_api: AsyncClient, assistant_api: AsyncClient
    ) -> None:
        created = await assistant_api.post(IDEAS, json={"text": "  Карта  снегового покрова "})
        idea_id = created.json()["id"]
        body = (await leader_api.get(IDEAS)).json()
        idea = next(each for each in body["items"] if each["id"] == idea_id)
        assert idea["text"] == "Карта снегового покрова"
        edit = await leader_api.put(
            f"{IDEAS}/{idea_id}", json={"text": "Карта снежного покрова", "version": 1}
        )
        assert edit.status_code == 204
        stale = await assistant_api.put(f"{IDEAS}/{idea_id}", json={"text": "Другое", "version": 1})
        assert stale.status_code == 409
        # Нулевой символ из вставки — отказ словами, а не ошибка базы.
        broken = await assistant_api.post(IDEAS, json={"text": "Идея\x00 из выгрузки"})
        assert broken.status_code == 422


@pytest.mark.infra
@pytest.mark.usefixtures("loaded")
class TestMaps:
    async def test_linked_nodes_carry_the_pult_step(self, leader_api: AsyncClient) -> None:
        board = (
            await leader_api.get(
                f"{MAPS}/{await map_id(leader_api, 'Мониторинг сельского хозяйства')}"
            )
        ).json()
        pult = (await leader_api.get("/api/v1/pult")).json()
        on_pult = {(row["section"], row["entity_id"]): row["step"] for row in pult["rows"]}
        section = {"project": "projects", "task": "tasks"}
        linked = [node for node in board["node_list"] if node["link"]]
        assert len(linked) == 4
        for node in linked:
            key = (section[node["link"]["type"]], node["link"]["id"])
            assert node["step"] == on_pult.get(key)
        note = next(node for node in linked if node["text"] == "Справка по засухе")
        assert note["step"] == "overdue"
        root = next(node for node in board["node_list"] if node["parent_id"] is None)
        assert root["text"] == "Мониторинг сельского хозяйства"

    async def test_nodes_add_move_parent_delete(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        board_id = await map_id(assistant_api, "Космическое образование")
        nodes = f"{MAPS}/{board_id}/nodes"
        board = (await assistant_api.get(f"{MAPS}/{board_id}")).json()
        root = next(node for node in board["node_list"] if node["parent_id"] is None)

        child = (
            await assistant_api.post(
                nodes, json={"text": "Летняя школа", "parent_id": root["id"], "x": 100, "y": 600}
            )
        ).json()["id"]
        grandchild = (
            await assistant_api.post(
                nodes, json={"text": "Программа", "parent_id": child, "x": 80, "y": 720}
            )
        ).json()["id"]
        moved = await assistant_api.put(
            f"{nodes}/{child}/position", json={"x": 140, "y": 640, "version": 1}
        )
        assert moved.status_code == 204
        far = await assistant_api.put(
            f"{nodes}/{child}/position", json={"x": 999_999, "y": 0, "version": 2}
        )
        assert far.status_code == 422
        # Корень не может стать потомком своего внука: связи замкнулись бы в кольцо.
        ring = await assistant_api.put(
            f"{nodes}/{root['id']}/parent", json={"parent_id": grandchild, "version": 1}
        )
        assert ring.status_code == 422

        # Удаляют ветвь только такой, какой её видел человек. Видел без внука — конфликт;
        # видел внука до правки второго пользователя — тоже конфликт: число узлов то же,
        # но подпись внука уже другая.
        child_id, grandchild_id = uuid.UUID(child), uuid.UUID(grandchild)
        without_grandchild = branch_stamp([(child_id, 2)])
        stale = await assistant_api.delete(
            f"{nodes}/{child}", params={"version": 2, "branch": without_grandchild}
        )
        assert stale.status_code == 409
        seen = branch_stamp([(child_id, 2), (grandchild_id, 1)])
        renamed = await assistant_api.put(
            f"{nodes}/{grandchild}", json={"text": "Программа смены", "version": 1}
        )
        assert renamed.status_code == 204
        edited = await assistant_api.delete(
            f"{nodes}/{child}", params={"version": 2, "branch": seen}
        )
        assert edited.status_code == 409
        fresh = branch_stamp([(child_id, 2), (grandchild_id, 2)])
        deleted = await assistant_api.delete(
            f"{nodes}/{child}", params={"version": 2, "branch": fresh}
        )
        assert deleted.json() == {"deleted": 2}
        left = await session.scalar(
            select(func.count()).select_from(MapNode).where(MapNode.map_id == uuid.UUID(board_id))
        )
        assert left == 4

    async def test_node_becomes_a_task_in_one_action(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        board_id = await map_id(leader_api, "Космическое образование")
        board = (await leader_api.get(f"{MAPS}/{board_id}")).json()
        contest = next(node for node in board["node_list"] if node["text"].startswith("Конкурс"))
        path = f"{MAPS}/{board_id}/nodes/{contest['id']}/convert"
        made = await leader_api.post(path, json={"kind": "task", "version": contest["version"]})
        assert made.status_code == 201, made.text
        task = await session.get(Task, uuid.UUID(made.json()["id"]))
        assert task is not None and task.title == contest["text"]

        board = (await leader_api.get(f"{MAPS}/{board_id}")).json()
        again = next(node for node in board["node_list"] if node["id"] == contest["id"])
        assert again["link"]["type"] == "task"
        twice = await leader_api.post(path, json={"kind": "task", "version": again["version"]})
        assert twice.status_code == 422

    async def test_new_map_and_mode(self, assistant_api: AsyncClient) -> None:
        created = await assistant_api.post(MAPS, json={"title": "Партнёры"})
        board_id = created.json()["id"]
        edit = await assistant_api.put(
            f"{MAPS}/{board_id}",
            json={"title": "Партнёры агентства", "mode": "structure", "version": 1},
        )
        assert edit.status_code == 204
        board = (await assistant_api.get(f"{MAPS}/{board_id}")).json()
        assert (board["title"], board["mode"], board["node_list"]) == (
            "Партнёры агентства",
            "structure",
            [],
        )
        # Список карт раздела показывает новую карту с новым режимом, а не прежнее название.
        listed = {
            each["id"]: (each["title"], each["mode"], each["nodes"], each["linked"])
            for each in (await assistant_api.get(IDEAS)).json()["maps"]
        }
        assert listed[board_id] == ("Партнёры агентства", "structure", 0, 0)


class TestRules:
    def test_ring_is_refused(self) -> None:
        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        parents: dict[uuid.UUID, uuid.UUID | None] = {a: None, b: a, c: b}
        check_parent(c, a, parents)
        with pytest.raises(RuleViolationError):
            check_parent(a, c, parents)
        with pytest.raises(RuleViolationError):
            check_parent(a, uuid.uuid4(), parents)

    def test_branch_stamp_matches_the_interface(self) -> None:
        # Тот же вектор проверяет `frontend/src/sections/ideas/stamp.test.ts`: расчёт один.
        a = uuid.UUID("00000000-0000-0000-0000-00000000000a")
        b = uuid.UUID("00000000-0000-0000-0000-00000000000b")
        assert branch_stamp([(b, 2), (a, 1)]) == branch_stamp([(a, 1), (b, 2)])
        assert branch_stamp([(a, 1), (b, 2)]) == "fe20735f"
        assert branch_stamp([]) == "811c9dc5"

    def test_subtree_takes_all_descendants(self) -> None:
        a, b, c, d = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        parents: dict[uuid.UUID, uuid.UUID | None] = {a: None, b: a, c: b, d: a}
        assert subtree(b, parents) == {b, c}
        assert subtree(a, parents) == {a, b, c, d}

    def test_awaiting_oldest_first(self) -> None:
        from datetime import UTC, date, datetime

        from app.domain.ideas import Waiting

        old, new = uuid.uuid4(), uuid.uuid4()
        answer = awaiting(
            [
                Waiting(
                    id=new, since=date(2026, 10, 3), sent_at=datetime(2026, 10, 3, 5, tzinfo=UTC)
                ),
                Waiting(
                    id=old, since=date(2026, 9, 25), sent_at=datetime(2026, 9, 25, 5, tzinfo=UTC)
                ),
            ],
            date(2026, 10, 5),
        )
        assert (answer.count, answer.oldest_days, answer.rows) == (2, 10, [old, new])
        # Возраст строки — из того же ответа, что «дольше всех»: у старшей они совпадают.
        assert answer.days == {old: 10, new: 2}
        # В один день — по моменту отправки, а не по идентификатору: утренняя раньше вечерней.
        morning = uuid.UUID(int=2**128 - 1)
        evening = uuid.UUID(int=0)
        same_day = awaiting(
            [
                Waiting(
                    id=evening,
                    since=date(2026, 10, 3),
                    sent_at=datetime(2026, 10, 3, 12, tzinfo=UTC),
                ),
                Waiting(
                    id=morning,
                    since=date(2026, 10, 3),
                    sent_at=datetime(2026, 10, 3, 4, tzinfo=UTC),
                ),
            ],
            date(2026, 10, 5),
        )
        assert same_day.oldest_id == morning
        empty = awaiting([], date(2026, 10, 5))
        assert (empty.count, empty.oldest_days, empty.oldest_id, empty.days) == (0, 0, None, {})
