"""Комментарии (ORB-016).

Три критерия карточки, и у каждого своё место, где он ломается тихо.

Мягкое удаление ломается тем, что реплика исчезает из ленты совсем. Тогда мягкое удаление
бессмысленно: оно и заводится ради следа. Проверяется не наличие строки в базе, а то, что
читатель видит след, — потому что база и так её хранит, а видит человек ленту.

Упоминание ломается тем, что «@Каримов» при двух Каримовых извещает кого-нибудь одного. В
агентстве однофамильцы есть, и предупредить не того человека о не его проекте хуже, чем не
предупредить никого.

Единый поток ломается тем, что в нём остаются только реплики: запрос к журналу изменений
отрабатывает, просто ничего не находит, — `entity_type` там хранится именем таблицы
(«projects»), а комментарии говорят «project». Проверка сверяет, что в ленте есть **оба**
вида событий, а не только тот, который проще получить.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.comments import find_mentions, validate_body
from app.domain.dictionaries import Priority, ProjectStatus
from app.domain.people import Role
from app.repos.models import Comment, Direction, Notification, Person, Project, User

pytestmark = pytest.mark.infra

API = "/api/v1"


async def a_project(session: AsyncSession, **overrides: Any) -> Project:
    direction = await session.scalar(select(Direction).limit(1))
    assert direction is not None

    fields: dict[str, Any] = {
        "code": f"PRJ-2026-{uuid.uuid4().int % 900 + 99:03d}",
        "title": "Проект для обсуждения",
        "kind": "project",
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


async def a_task(api: AsyncClient, title: str = "Задача для обсуждения") -> str:
    response = await api.post(
        f"{API}/tasks", json={"title": title, "priority_code": Priority.NORMAL.value}
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def a_comment(
    api: AsyncClient, entity_type: str, entity_id: str, body: str
) -> dict[str, Any]:
    response = await api.post(
        f"{API}/comments",
        json={"entity_type": entity_type, "entity_id": entity_id, "body": body},
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def a_person(session: AsyncSession, full_name: str, **overrides: Any) -> Person:
    person = Person(full_name=full_name, **overrides)
    session.add(person)
    await session.flush()
    return person


class TestCommentsOnBothKinds:
    async def test_a_comment_lands_on_a_project(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)

        created = await a_comment(
            assistant_api, "project", str(project.id), "Подрядчик вышел на площадку"
        )

        assert created["body"] == "Подрядчик вышел на площадку"
        listed = await assistant_api.get(
            f"{API}/comments", params={"entity_type": "project", "entity_id": str(project.id)}
        )
        assert [item["body"] for item in listed.json()] == ["Подрядчик вышел на площадку"]

    async def test_a_comment_lands_on_a_task(self, assistant_api: AsyncClient) -> None:
        task = await a_task(assistant_api)

        await a_comment(assistant_api, "task", task, "Антенна приехала")

        listed = await assistant_api.get(
            f"{API}/comments", params={"entity_type": "task", "entity_id": task}
        )
        assert [item["body"] for item in listed.json()] == ["Антенна приехала"]

    async def test_a_comment_on_a_missing_record_is_refused(
        self, assistant_api: AsyncClient
    ) -> None:
        """Реплика-сирота не видна ни в одной ленте и всплывает при переносе данных."""
        refused = await assistant_api.post(
            f"{API}/comments",
            json={"entity_type": "task", "entity_id": str(uuid.uuid4()), "body": "В пустоту"},
        )

        assert refused.status_code == 404

    async def test_an_empty_comment_is_refused(self, assistant_api: AsyncClient) -> None:
        task = await a_task(assistant_api)

        refused = await assistant_api.post(
            f"{API}/comments",
            json={"entity_type": "task", "entity_id": task, "body": "   "},
        )

        assert refused.status_code == 422, refused.text

    async def test_the_leader_reads_but_does_not_write(
        self, leader_api: AsyncClient, assistant_api: AsyncClient
    ) -> None:
        """Руководитель видит обсуждение и не участвует в нём (ADR-0011).

        Его единственная запись — решение по проекту на контроле (ORB-062), и она придёт
        своим путём, а не через общую ленту.
        """
        task = await a_task(assistant_api)
        await a_comment(assistant_api, "task", task, "Видно обоим")

        listed = await leader_api.get(
            f"{API}/comments", params={"entity_type": "task", "entity_id": task}
        )
        assert listed.status_code == 200
        assert [item["body"] for item in listed.json()] == ["Видно обоим"]

        refused = await leader_api.post(
            f"{API}/comments",
            json={"entity_type": "task", "entity_id": task, "body": "И моё слово"},
        )
        assert refused.status_code == 403


class TestEditingAndSoftDeleting:
    async def test_the_author_edits_and_the_edit_is_visible_as_such(
        self, assistant_api: AsyncClient
    ) -> None:
        """Отметка о правке отдельно от «когда обновлялась строка».

        Читателю важно не время записи, а то, что текст не тот, что был написан сначала.
        """
        task = await a_task(assistant_api)
        created = await a_comment(assistant_api, "task", task, "Сроки сдвигаются")
        assert created["edited_at"] is None

        edited = await assistant_api.patch(
            f"{API}/comments/{created['id']}", json={"body": "Сроки сдвигаются на неделю"}
        )

        assert edited.status_code == 200, edited.text
        assert edited.json()["body"] == "Сроки сдвигаются на неделю"
        assert edited.json()["edited_at"] is not None

    async def test_a_deleted_comment_leaves_a_trace_without_its_text(
        self, assistant_api: AsyncClient
    ) -> None:
        """Мягкое удаление заводится ради следа — иначе оно не отличается от обычного.

        Пропуск в переписке делает соседние реплики непонятными: читатель не может
        отличить «здесь ничего не было» от «здесь было и убрали».
        """
        task = await a_task(assistant_api)
        first = await a_comment(assistant_api, "task", task, "Первое")
        await a_comment(assistant_api, "task", task, "Второе")

        removed = await assistant_api.delete(f"{API}/comments/{first['id']}")
        assert removed.status_code == 204

        listed = (
            await assistant_api.get(
                f"{API}/comments", params={"entity_type": "task", "entity_id": task}
            )
        ).json()

        assert len(listed) == 2, "удалённая реплика исчезла из ленты"
        gone = next(item for item in listed if item["id"] == first["id"])
        assert gone["body"] is None
        assert gone["deleted_at"] is not None

    async def test_the_text_survives_in_the_database(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Удаление мягкое: строка и текст остаются, наружу не выдаются."""
        task = await a_task(assistant_api)
        created = await a_comment(assistant_api, "task", task, "Сказанное не вырубишь")

        await assistant_api.delete(f"{API}/comments/{created['id']}")

        stored = await session.get(Comment, uuid.UUID(created["id"]))
        assert stored is not None
        assert stored.body == "Сказанное не вырубишь"

    async def test_deleting_twice_is_not_an_error(self, assistant_api: AsyncClient) -> None:
        """Человек нажал дважды — второй отказ ему ничего не объясняет."""
        task = await a_task(assistant_api)
        created = await a_comment(assistant_api, "task", task, "Раз")

        assert (await assistant_api.delete(f"{API}/comments/{created['id']}")).status_code == 204
        assert (await assistant_api.delete(f"{API}/comments/{created['id']}")).status_code == 204

    async def test_a_deleted_comment_is_not_edited_back_to_life(
        self, assistant_api: AsyncClient
    ) -> None:
        task = await a_task(assistant_api)
        created = await a_comment(assistant_api, "task", task, "Было")
        await assistant_api.delete(f"{API}/comments/{created['id']}")

        refused = await assistant_api.patch(
            f"{API}/comments/{created['id']}", json={"body": "Стало"}
        )

        assert refused.status_code == 422, refused.text

    async def test_a_missing_comment_is_not_found(self, assistant_api: AsyncClient) -> None:
        """Реплика, удалённая в другой вкладке, — это «не найдено», а не поломка."""
        gone = await assistant_api.patch(
            f"{API}/comments/{uuid.uuid4()}", json={"body": "В никуда"}
        )

        assert gone.status_code == 404

    async def test_someone_elses_comment_is_not_editable(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Сегодня пишет один человек, но резолюция руководителя (ORB-062) ляжет в ту же
        ленту за его подписью — и «только автор» станет единственным, что её защищает."""
        task = await a_task(assistant_api)
        created = await a_comment(assistant_api, "task", task, "Моё")

        leader = await session.scalar(select(User).where(User.role == Role.LEADER))
        assert leader is not None
        stored = await session.get(Comment, uuid.UUID(created["id"]))
        assert stored is not None
        stored.author_id = leader.id
        await session.flush()

        refused = await assistant_api.patch(
            f"{API}/comments/{created['id']}", json={"body": "Не моё"}
        )

        assert refused.status_code == 403, refused.text


class TestMentionsNotify:
    async def test_a_mention_creates_a_notification_for_the_other_user(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Извещается второй пользователь, а не упомянутый (Q25).

        Сотрудники в систему не входят (ADR-0011), и показать им внутри неё нечего. Кого
        упомянули — сохраняется, чтобы доставку можно было изменить без потери данных.
        """
        person = await a_person(session, "Рахимов Рустам Акмалович")
        task = await a_task(assistant_api)

        await a_comment(assistant_api, "task", task, "Прошу @Рахимов посмотреть смету")

        notifications = list(await session.scalars(select(Notification)))
        assert len(notifications) == 1
        assert notifications[0].kind == "mention"
        assert notifications[0].payload["person_id"] == str(person.id)
        assert notifications[0].payload["person_name"] == "Рахимов Рустам Акмалович"

    async def test_the_author_is_not_notified_about_their_own_words(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        await a_person(session, "Рахимов Рустам Акмалович")
        task = await a_task(assistant_api)

        await a_comment(assistant_api, "task", task, "@Рахимов, ваш ход")

        authors = {
            notification.payload["author_id"]
            for notification in await session.scalars(select(Notification))
        }
        recipients = {
            str(notification.user_id)
            for notification in await session.scalars(select(Notification))
        }
        assert authors.isdisjoint(recipients), "автор извещён о собственной реплике"

    async def test_an_ambiguous_mention_notifies_nobody(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Однофамильцы: предупредить не того хуже, чем не предупредить никого.

        Первое выглядит как утечка, второе — как забывчивость автора, который видит свой
        текст и может дописать имя.
        """
        await a_person(session, "Каримов Азиз Фарходович")
        await a_person(session, "Каримов Бекзод Шухратович")
        task = await a_task(assistant_api)

        created = await a_comment(assistant_api, "task", task, "@Каримов посмотрите")

        assert created["mentioned"] == []
        assert await session.scalar(select(func.count()).select_from(Notification)) == 0

    async def test_a_similar_surname_is_not_the_same_surname(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """«Каримов» и «Каримова» — разные слова и разные люди.

        Соседняя проверка требует молчать при двусмысленности; эта — не считать
        двусмысленностью то, что ею не является. Иначе «молчать, когда неясно»
        выродится в «молчать почти всегда», и упоминания перестанут работать вовсе.
        """
        karimov = await a_person(session, "Каримов Азиз Фарходович")
        await a_person(session, "Каримова Дилноза Шавкатовна")
        task = await a_task(assistant_api)

        created = await a_comment(assistant_api, "task", task, "@Каримов посмотрите")

        assert [person["id"] for person in created["mentioned"]] == [str(karimov.id)]

    async def test_a_partial_name_matches_nobody(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """«@Рах» не Рахимов: совпадение по части слова однажды поймало бы не того."""
        await a_person(session, "Рахимов Рустам Акмалович")
        task = await a_task(assistant_api)

        created = await a_comment(assistant_api, "task", task, "@Рах, посмотрите")

        assert created["mentioned"] == []

    async def test_a_dismissed_employee_is_not_mentioned(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Уволившемуся не пишут: упоминание его не вернёт, а уведомление уйдёт впустую."""
        await a_person(session, "Ушедший Улугбек Уралович", is_active=False)
        task = await a_task(assistant_api)

        created = await a_comment(assistant_api, "task", task, "@Ушедший, где отчёт")

        assert created["mentioned"] == []

    async def test_editing_the_same_mention_does_not_notify_twice(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Правка запятой не должна звонить человеку второй раз (инвариант 6)."""
        await a_person(session, "Рахимов Рустам Акмалович")
        task = await a_task(assistant_api)
        created = await a_comment(assistant_api, "task", task, "@Рахимов посмотрите")
        before = await session.scalar(select(func.count()).select_from(Notification))

        await assistant_api.patch(
            f"{API}/comments/{created['id']}", json={"body": "@Рахимов, посмотрите, пожалуйста"}
        )

        assert await session.scalar(select(func.count()).select_from(Notification)) == before

    async def test_the_same_name_twice_in_one_text_is_one_mention(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        await a_person(session, "Рахимов Рустам Акмалович")
        task = await a_task(assistant_api)

        created = await a_comment(
            assistant_api, "task", task, "@Рахимов, и ещё раз @Рахимов — по смете"
        )

        assert len(created["mentioned"]) == 1
        assert await session.scalar(select(func.count()).select_from(Notification)) == 1

    async def test_a_mention_with_nobody_to_tell_is_not_an_error(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Некому сказать — значит некому, а не «ошибка сохранения».

        Второй пользователь может быть отключён: реплика при этом обязана сохраниться,
        а уведомление — просто не появиться. Потерять текст из-за того, что его некому
        показать, хуже, чем не показать.
        """
        await a_person(session, "Рахимов Рустам Акмалович")
        for user in await session.scalars(select(User).where(User.role == Role.LEADER)):
            user.is_active = False
        await session.flush()
        task = await a_task(assistant_api)

        created = await a_comment(assistant_api, "task", task, "@Рахимов, посмотрите")

        assert created["body"] == "@Рахимов, посмотрите"
        assert await session.scalar(select(func.count()).select_from(Notification)) == 0

    def test_punctuation_is_not_part_of_a_name(self) -> None:
        """«@Рахимов,» — это Рахимов и запятая, а не человек с запятой в фамилии."""
        assert find_mentions("@Рахимов, @Каримов!") == ["Рахимов", "Каримов"]
        assert find_mentions("почта@example.com") == ["example.com"]
        assert find_mentions("без упоминаний") == []
        assert find_mentions("@я") == [], "две буквы минимум: «@я» — опечатка, а не обращение"

    def test_an_empty_body_is_refused_in_the_domain(self) -> None:
        assert validate_body("  текст  ") == "текст"
        with pytest.raises(ValueError):
            validate_body("   ")
        with pytest.raises(ValueError):
            validate_body("а" * 5001)


class TestTimelineIsOneStream:
    async def test_comments_and_changes_stand_in_one_column(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Критерий: лента комментариев и история изменений — один хронологический поток.

        Сломать это легко и незаметно: запрос к журналу отрабатывает и ничего не находит,
        потому что там `entity_type` хранится именем таблицы. Лента при этом выглядит
        целой — в ней просто нет изменений.
        """
        task = await a_task(assistant_api)
        await assistant_api.patch(f"{API}/tasks/{task}", json={"title": "Переименованная"})
        await a_comment(assistant_api, "task", task, "Переименовал, чтобы было понятнее")

        timeline = await assistant_api.get(
            f"{API}/timeline", params={"entity_type": "task", "entity_id": task}
        )

        assert timeline.status_code == 200, timeline.text
        events = timeline.json()

        assert any(event["kind"] == "comment" for event in events), "в ленте нет реплик"

        # Изменение **самой задачи**, а не реплики: правка комментария тоже попадает в
        # журнал, и проверка «есть хоть одно изменение» прошла бы даже тогда, когда
        # изменения задачи не находятся вовсе. Текст реплики в журнал не пишется, поэтому
        # непустое `changes` бывает только у настоящей записи.
        renames = [
            event
            for event in events
            if event["kind"] == "change" and (event["changes"] or {}).get("title")
        ]
        assert renames, "в ленте нет изменений самой задачи — журнал не нашёлся"
        assert any(event["changes"]["title"]["to"] == "Переименованная" for event in renames), (
            "переименование задачи в ленту не попало"
        )

    async def test_events_come_in_the_order_they_happened(self, assistant_api: AsyncClient) -> None:
        """Ленту читают сверху вниз как разговор, а не как список новостей."""
        task = await a_task(assistant_api)
        await a_comment(assistant_api, "task", task, "Первое слово")
        await assistant_api.patch(f"{API}/tasks/{task}", json={"title": "Другое имя"})
        await a_comment(assistant_api, "task", task, "Последнее слово")

        events = (
            await assistant_api.get(
                f"{API}/timeline", params={"entity_type": "task", "entity_id": task}
            )
        ).json()

        moments = [event["at"] for event in events]
        assert moments == sorted(moments)
        bodies = [event["comment"]["body"] for event in events if event["kind"] == "comment"]
        assert bodies == ["Первое слово", "Последнее слово"]

    async def test_a_comment_appears_in_the_stream_once(self, assistant_api: AsyncClient) -> None:
        """Реплика — одно событие, а не два.

        Найдено на живом стенде, а не проверками: каждая реплика шла в ленте дважды —
        своим текстом и строкой журнала «[created] body, author_id, entity_id,
        entity_type». Поток удлинялся вдвое, не добавляя ничего: перечень имён полей не
        говорит читателю того, чего не сказал сам текст. Критерий тикета — читаемая лента,
        и вдвое более длинная ему не отвечает.
        """
        task = await a_task(assistant_api)
        await a_comment(assistant_api, "task", task, "Единственная реплика")

        events = (
            await assistant_api.get(
                f"{API}/timeline", params={"entity_type": "task", "entity_id": task}
            )
        ).json()

        about_comment = [
            event
            for event in events
            if event["kind"] == "comment"
            or (event["subject"] == "comments" and event["action"] == "created")
        ]
        assert len(about_comment) == 1, f"реплика попала в ленту {len(about_comment)} раза"

    async def test_an_edit_and_a_deletion_still_show_up(self, assistant_api: AsyncClient) -> None:
        """Появление реплики из журнала убрано, правка и удаление — остались.

        Иначе вместе с задвоением ушло бы и то, ради чего журнал вообще нужен: кто и
        когда поправил или убрал сказанное.
        """
        task = await a_task(assistant_api)
        first = await a_comment(assistant_api, "task", task, "Будет правлена")
        second = await a_comment(assistant_api, "task", task, "Будет удалена")
        await assistant_api.patch(f"{API}/comments/{first['id']}", json={"body": "Поправлена"})
        await assistant_api.delete(f"{API}/comments/{second['id']}")

        events = (
            await assistant_api.get(
                f"{API}/timeline", params={"entity_type": "task", "entity_id": task}
            )
        ).json()

        updates = [
            event for event in events if event["kind"] == "change" and event["action"] == "updated"
        ]
        assert len(updates) >= 2, "правка и удаление реплики из ленты пропали"

    async def test_the_stream_names_who_did_it(self, assistant_api: AsyncClient) -> None:
        """Без имени действующего лица лента отвечает «что», но не «кто»."""
        task = await a_task(assistant_api)
        await a_comment(assistant_api, "task", task, "Моя реплика")

        events = (
            await assistant_api.get(
                f"{API}/timeline", params={"entity_type": "task", "entity_id": task}
            )
        ).json()

        assert all(event["actor_name"] for event in events)

    async def test_editing_a_comment_shows_up_as_a_change(self, assistant_api: AsyncClient) -> None:
        """«Написал» и «поправил написанное» — разные события, и второе без первого не
        читается."""
        task = await a_task(assistant_api)
        created = await a_comment(assistant_api, "task", task, "Было так")
        await assistant_api.patch(f"{API}/comments/{created['id']}", json={"body": "Стало так"})

        events = (
            await assistant_api.get(
                f"{API}/timeline", params={"entity_type": "task", "entity_id": task}
            )
        ).json()

        changes = [event for event in events if event["kind"] == "change"]
        assert any(event["action"] == "updated" for event in changes)

    async def test_the_journal_keeps_no_copy_of_the_text(self, assistant_api: AsyncClient) -> None:
        """Журналу нужен ответ «кто и когда»; «что написано» лежит в самой реплике.

        Второе место хранения того же текста означало бы, что комментарий к проекту с
        грифом расползается по таблицам, из которых его уже не вычистить (ADR-0007).
        """
        task = await a_task(assistant_api)
        created = await a_comment(assistant_api, "task", task, "Особо секретное слово")
        await assistant_api.patch(
            f"{API}/comments/{created['id']}", json={"body": "Другое секретное слово"}
        )

        events = (
            await assistant_api.get(
                f"{API}/timeline", params={"entity_type": "task", "entity_id": task}
            )
        ).json()

        recorded = str([event["changes"] for event in events if event["kind"] == "change"])
        assert "Особо секретное слово" not in recorded
        assert "Другое секретное слово" not in recorded

    async def test_a_timeline_of_a_missing_record_is_not_an_empty_list(
        self, assistant_api: AsyncClient
    ) -> None:
        missing = await assistant_api.get(
            f"{API}/timeline", params={"entity_type": "task", "entity_id": str(uuid.uuid4())}
        )

        assert missing.status_code == 404


class TestDiscussionGoesWithTheRecord:
    async def test_deleting_a_task_takes_its_comments(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Внешним ключом это не выражается, поэтому и проверяется отдельно.

        Забыть вызов уборки — значит оставить в базе реплики, которых не видно ни в одной
        ленте, и обнаружить их при первом переносе данных.
        """
        task = await a_task(assistant_api)
        await a_comment(assistant_api, "task", task, "Пропадёт вместе с задачей")

        await assistant_api.delete(f"{API}/tasks/{task}")

        left = await session.scalar(
            select(func.count()).select_from(Comment).where(Comment.entity_id == uuid.UUID(task))
        )
        assert left == 0

    async def test_deleting_a_project_takes_the_comments_of_its_tasks_too(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Задачи уносит сама база каскадом, а их обсуждения — нет.

        Это и есть место, где реплики осели бы навсегда: проект удалён, задач нет, а
        комментарии к ним остались и не видны ниоткуда.
        """
        project = await a_project(session)
        created = await assistant_api.post(
            f"{API}/tasks",
            json={
                "title": "Задача проекта",
                "project_id": str(project.id),
                "priority_code": Priority.NORMAL.value,
            },
        )
        task_id = str(created.json()["id"])
        await a_comment(assistant_api, "task", task_id, "Реплика к задаче проекта")
        await a_comment(assistant_api, "project", str(project.id), "Реплика к проекту")

        await assistant_api.delete(f"{API}/projects/{project.id}")

        assert await session.scalar(select(func.count()).select_from(Comment)) == 0
