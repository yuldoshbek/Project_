"""Журнал изменений (ORB-009, ADR-0010).

Проверяется не «пишется ли что-нибудь», а четыре обещания, каждое из которых при
нарушении делает журнал бесполезным ровно тогда, когда он нужен.

Запись содержит **только изменившееся поле**, а не снимок целиком: снимок раздувает
журнал и выносит наружу данные, которых в записи быть не должно. Запись живёт в той же
транзакции, что и изменение: иначе журнал показывает правки, которых не было. Содержимое
закрытой записи заменяется маркером, но сам факт изменения остаётся: иначе закрытый
проект можно менять бесследно. И, наконец, запись нельзя ни исправить, ни удалить, ни
стереть таблицу целиком — это проверяется попыткой, а не чтением исходников миграции.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum

import pytest
from fastapi import APIRouter, FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.api.security import Assistant
from app.domain.audit import MASK, ActorKind, AuditAction, mask_changes
from app.repos.models import AuditLog, Person, User
from app.services.audit import Actor, _plain, set_actor

pytestmark = pytest.mark.infra


async def entries_for(session: AsyncSession, entity_id: uuid.UUID) -> list[AuditLog]:
    result = await session.scalars(
        select(AuditLog).where(AuditLog.entity_id == entity_id).order_by(AuditLog.occurred_at)
    )
    return list(result)


@pytest.fixture
async def person(session: AsyncSession) -> Person:
    subject = Person(full_name="Азиз Каримов", position="Начальник управления")
    session.add(subject)
    await session.flush()
    return subject


@pytest.fixture(autouse=True)
async def neutral_actor() -> AsyncIterator[None]:
    """Каждый тест начинается без назначенного действующего лица.

    Контекстная переменная переживает тест, и оставленный от соседа помощник превратил бы
    проверку «изменение без пользователя приписывается заданию» в ложно-зелёную.
    """
    set_actor(Actor())
    yield
    set_actor(Actor())


# Пишущий маршрут для проверки проводки: своих пишущих эндпоинтов пока нет, первым
# станет ORB-011.
_probe = APIRouter()


@_probe.post("/probe/person", status_code=201, summary="Пробное создание сотрудника")
async def _probe_person(user: Assistant, session: SessionDep) -> dict[str, str]:
    subject = Person(full_name="Создан через интерфейс")
    session.add(subject)
    await session.flush()
    return {"id": str(subject.id)}


class TestOnlyWhatChanged:
    async def test_one_changed_field_gives_one_entry_about_that_field(
        self, session: AsyncSession, person: Person
    ) -> None:
        before = len(await entries_for(session, person.id))

        person.position = "Заместитель начальника управления"
        await session.flush()

        entries = await entries_for(session, person.id)
        assert len(entries) == before + 1

        changes = entries[-1].changes
        assert list(changes) == ["position"], "в записи оказалось лишнее поле"
        assert changes["position"] == {
            "from": "Начальник управления",
            "to": "Заместитель начальника управления",
        }
        assert entries[-1].action == AuditAction.UPDATED

    async def test_assigning_the_same_value_is_not_a_change(
        self, session: AsyncSession, person: Person
    ) -> None:
        """Иначе журнал заполняется шумом, и в нём перестают искать."""
        before = len(await entries_for(session, person.id))

        person.position = person.position
        person.full_name = person.full_name
        await session.flush()

        assert len(await entries_for(session, person.id)) == before

    async def test_equal_value_from_another_object_is_not_a_change(
        self, session: AsyncSession, person: Person
    ) -> None:
        """Равное значение, но другой объект.

        Так приходят даты и перечисления после разбора запроса: значение то же, объект
        новый. Сравнение по совпадению, а не по тождеству, — единственное, что не даёт
        журналу заполниться записями «срок изменён с 5 марта на 5 марта».
        """
        before = len(await entries_for(session, person.id))

        person.position = "".join(list(person.position or ""))
        await session.flush()

        assert len(await entries_for(session, person.id)) == before

    async def test_creation_is_recorded_with_the_filled_fields(self, session: AsyncSession) -> None:
        """У новой записи «было» не существует, и без значений запись бессодержательна."""
        subject = Person(full_name="Дилноза Рахимова", department="Международное сотрудничество")
        session.add(subject)
        await session.flush()

        entries = await entries_for(session, subject.id)
        assert len(entries) == 1
        assert entries[0].action == AuditAction.CREATED
        assert entries[0].changes["full_name"]["to"] == "Дилноза Рахимова"
        assert entries[0].changes["full_name"]["from"] is None
        assert "position" not in entries[0].changes, "незаполненное поле в журнале лишнее"

    async def test_entities_without_the_mark_are_not_logged(self, session: AsyncSession) -> None:
        """Журналируется деловая запись, а не всё подряд.

        Токены сессии и счётчик неудачных входов меняются на каждом шаге входа; попади
        они в журнал, деловые изменения утонули бы в служебных.
        """
        user = await session.scalar(select(User).limit(1))
        assert user is not None
        before = await session.scalar(select(func.count()).select_from(AuditLog))

        user.failed_login_count = 3
        await session.flush()

        assert await session.scalar(select(func.count()).select_from(AuditLog)) == before


class TestDeletion:
    async def test_deletion_is_recorded_as_an_event_without_values(
        self, session: AsyncSession, person: Person
    ) -> None:
        """Значения не переписываются в журнал.

        Деловые записи не удаляются, а уходят в архив (ORB-025); прямое удаление —
        событие, а не изменение содержимого. Копировать в журнал всю запись перед
        удалением означало бы держать вторую копию данных там, где её никто не ждёт.
        """
        person_id = person.id

        await session.delete(person)
        await session.flush()

        entries = await entries_for(session, person_id)
        assert [entry.action for entry in entries] == [AuditAction.CREATED, AuditAction.DELETED]
        assert entries[-1].changes == {}


class TestValuesSurviveTheJournal:
    """Значение обязано пережить запись в JSONB и чтение обратно.

    Проверяется отдельно от целых сценариев: сроки, признаки и ссылки приходят в журнал
    не строками, а датой, перечислением и идентификатором. Незамеченная здесь ошибка
    проявится записью вида «срок изменён с datetime.date(2026, 3, 5) на …».
    """

    def test_primitives_pass_through_unchanged(self) -> None:
        assert _plain(None) is None
        assert _plain(True) is True
        assert _plain(42) == 42
        assert _plain("Спутник") == "Спутник"

    def test_dates_become_iso_strings(self) -> None:
        assert _plain(date(2026, 3, 5)) == "2026-03-05"
        assert _plain(datetime(2026, 3, 5, 14, 30, tzinfo=UTC)) == "2026-03-05T14:30:00+00:00"

    def test_identifiers_and_numbers_become_strings(self) -> None:
        identifier = uuid.uuid4()

        assert _plain(identifier) == str(identifier)
        assert _plain(Decimal("10.50")) == "10.50"

    def test_enumerations_give_their_value_not_their_name(self) -> None:
        """`<ActorKind.HUMAN: 'human'>` в журнале сделал бы его нечитаемым.

        Перечисления проекта — `StrEnum`, и они проходят строковой веткой. Отдельная
        ветка нужна для обычного `Enum`: без неё он записался бы своим `repr`.
        """
        assert _plain(ActorKind.HUMAN) == "human"
        assert _plain(AuditAction.UPDATED) == "updated"

        class Colour(Enum):
            RED = 1

        assert _plain(Colour.RED) == 1

    def test_anything_else_is_written_readably_rather_than_dropped(self) -> None:
        """Неизвестный тип не должен ронять запись: журнал важнее аккуратности значения."""

        class Odd:
            def __repr__(self) -> str:
                return "<нечто>"

        assert _plain(Odd()) == "<нечто>"


class TestSameTransaction:
    async def test_rolling_back_the_change_rolls_back_the_record_of_it(
        self, session: AsyncSession, person: Person
    ) -> None:
        """Журнал в отдельной транзакции показывал бы правки, которых не было."""
        person_id = person.id

        savepoint = await session.begin_nested()
        person.position = "Советник"
        await session.flush()
        assert len(await entries_for(session, person_id)) == 2, "запись не появилась вовсе"
        await savepoint.rollback()

        entries = await entries_for(session, person_id)
        assert [entry.action for entry in entries] == [AuditAction.CREATED]


class TestActor:
    async def test_change_without_a_named_actor_is_attributed_to_a_job(
        self, session: AsyncSession, person: Person
    ) -> None:
        """Не человеку. Изменение, за которое никто не назвался, — фоновое."""
        entries = await entries_for(session, person.id)

        assert entries[0].actor_kind == ActorKind.JOB
        assert entries[0].actor_id is None

    async def test_named_actor_is_recorded(self, session: AsyncSession) -> None:
        user = await session.scalar(select(User).limit(1))
        assert user is not None
        set_actor(Actor(id=user.id, kind=ActorKind.HUMAN, ip="10.0.0.7"))

        subject = Person(full_name="Шухрат Юсупов")
        session.add(subject)
        await session.flush()

        entry = (await entries_for(session, subject.id))[0]
        assert entry.actor_kind == ActorKind.HUMAN
        assert entry.actor_id == user.id
        assert entry.ip == "10.0.0.7"


class TestActorComesFromTheRequest:
    """Проводка от входа в запрос до строки журнала, а не только сама функция."""

    async def test_change_made_through_the_api_is_attributed_to_the_signed_in_user(
        self, app: FastAPI, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        app.include_router(_probe, prefix="/api/v1")

        created = await assistant_api.post("/api/v1/probe/person")
        assert created.status_code == 201, created.text

        entry = (await entries_for(session, uuid.UUID(created.json()["id"])))[0]
        assert entry.actor_kind == ActorKind.HUMAN
        assert entry.actor_id is not None, "изменение помощника приписано фоновому заданию"

        expected = await session.scalar(select(User).where(User.id == entry.actor_id))
        assert expected is not None and expected.role == "assistant"


class TestClassifiedContent:
    def test_masking_keeps_the_field_names_and_hides_the_values(self) -> None:
        masked = mask_changes({"title": {"from": "Спутник", "to": "Спутник-2"}})

        assert masked == {"title": {"from": MASK, "to": MASK}}

    async def test_classified_entity_is_logged_without_values(
        self, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Факт изменения фиксируется, содержимое — нет (ADR-0007).

        Гриф появляется у проектов в ORB-011; здесь он подставляется, чтобы проверить
        саму проводку, а не только чистую функцию маскирования.
        """
        monkeypatch.setattr(Person, "audit_hides_values", True)

        subject = Person(full_name="Закрытая запись", position="Не для журнала")
        session.add(subject)
        await session.flush()

        entry = (await entries_for(session, subject.id))[0]
        assert set(entry.changes) >= {"full_name", "position"}, "факт изменения обязан остаться"
        assert all(side == MASK for sides in entry.changes.values() for side in sides.values()), (
            "значение закрытой записи попало в журнал"
        )


class TestTheRecordCannotBeUndone:
    """Проверяется попыткой, а не чтением миграции.

    Защита, о которой известно только из исходников, — это не защита, а намерение.
    """

    async def test_update_is_refused_by_the_database(
        self, session: AsyncSession, person: Person
    ) -> None:
        entry = (await entries_for(session, person.id))[0]

        savepoint = await session.begin_nested()
        with pytest.raises(DBAPIError, match="неизменяем"):
            await session.execute(
                text("UPDATE audit_log SET action = 'подделка' WHERE id = :id"),
                {"id": entry.id},
            )
        await savepoint.rollback()

    async def test_delete_is_refused_by_the_database(
        self, session: AsyncSession, person: Person
    ) -> None:
        entry = (await entries_for(session, person.id))[0]

        savepoint = await session.begin_nested()
        with pytest.raises(DBAPIError, match="неизменяем"):
            await session.execute(text("DELETE FROM audit_log WHERE id = :id"), {"id": entry.id})
        await savepoint.rollback()

    async def test_truncate_is_refused_by_the_database(self, session: AsyncSession) -> None:
        """TRUNCATE обходит построчные триггеры — без отдельной защиты журнал стирается
        одной командой, и обе предыдущие проверки становятся декорацией."""
        savepoint = await session.begin_nested()
        with pytest.raises(DBAPIError, match="неизменяем"):
            await session.execute(text("TRUNCATE audit_log"))
        await savepoint.rollback()


class TestWritingIsNotUpToTheCaller:
    def test_no_route_writes_to_the_journal_by_hand(self) -> None:
        """Точечные вызовы из роутеров запрещены — их забывают (ADR-0010).

        Проверяется не наличием сервиса, а отсутствием обращений к журналу из слоя API:
        первый же такой вызов означает, что рядом появится место, где его забыли.
        """
        from pathlib import Path

        api = Path(__file__).resolve().parent.parent / "app" / "api"
        offenders = [
            path.relative_to(api).as_posix()
            for path in api.rglob("*.py")
            if "AuditLog" in path.read_text(encoding="utf-8")
        ]

        assert not offenders, f"журнал пишется из слоя API: {offenders}"
