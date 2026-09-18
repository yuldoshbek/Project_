"""Пользователи системы и сотрудники агентства.

Главное здесь — что это два разных понятия. Смешение обнаруживается не сразу: система
работает, но в таблице пользователей оказываются сорок человек, которые никогда не войдут,
и появляются права, которые никто не проверяет.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import seed as seed_module
from app.domain.people import Role
from app.repos.models import Person, User

pytestmark = pytest.mark.infra


class TestSeededUsers:
    async def test_exactly_two_accounts(self, session: AsyncSession) -> None:
        """Пользователей двое: помощник и руководитель (ADR-0011)."""
        roles = sorted(await session.scalars(select(User.role)))

        assert roles == [Role.ASSISTANT, Role.LEADER]

    async def test_accounts_carry_no_secrets(self) -> None:
        """У учётной записи нет ни одного поля, похожего на секрет или на вход.

        Проверяются **обрывки имён**, а не список колонок: список пришлось бы дополнять
        руками, а обрывок ловит и то, что добавят завтра. Входа в системе нет (ADR-0026),
        репозиторий публичный, и любой секрет в схеме однажды окажется в сидах.
        """
        suspicious = ("password", "secret", "token", "login", "locked")
        offenders = [
            column.name
            for column in User.__table__.columns
            for fragment in suspicious
            if fragment in column.name.lower()
        ]

        assert not offenders, f"в учётной записи остались поля входа: {offenders}"

    async def test_no_staff_records_are_invented(self, session: AsyncSession) -> None:
        """Сотрудники агентства сидами не заполняются: это реальные люди.

        Выдуманные записи пришлось бы вычищать перед эксплуатацией, и часть наверняка
        осталась бы — в системе государственного органа.
        """
        total = await session.scalar(select(func.count()).select_from(Person))

        assert total == 0

    async def test_re_seeding_does_not_reset_accounts(self, session: AsyncSession) -> None:
        """Повторный запуск сидов не трогает существующие учётные записи."""
        user = await session.scalar(select(User).where(User.email == "assistant@orbita.local"))
        assert user is not None
        user.locale = "uz-Cyrl"
        user.is_active = False
        await session.flush()

        await seed_module.seed(session)

        await session.refresh(user)
        assert user.locale == "uz-Cyrl"
        assert user.is_active is False


class TestUserRules:
    async def test_email_is_case_insensitive_and_unique(self, session: AsyncSession) -> None:
        """Адрес — это логин.

        `citext` нужен именно здесь: человек, набравший заглавную первую букву, должен
        войти, а не завести вторую учётную запись.
        """
        session.add(User(email="Ivan@orbita.local", full_name="Иван", role=Role.ASSISTANT))
        await session.flush()

        session.add(User(email="ivan@orbita.local", full_name="Он же", role=Role.LEADER))

        with pytest.raises(IntegrityError):
            await session.flush()

    async def test_user_can_exist_without_staff_record(self, session: AsyncSession) -> None:
        """Связь с карточкой сотрудника необязательна: пользователя заводят и без неё."""
        user = User(email="new@orbita.local", full_name="Новый", role=Role.ASSISTANT)
        session.add(user)
        await session.flush()

        assert user.person_id is None
        assert user.person is None

    async def test_removing_staff_record_keeps_the_account(self, session: AsyncSession) -> None:
        """Удаление карточки сотрудника не удаляет пользователя.

        Иначе увольнение сотрудника уносило бы вместе с ним учётную запись, а с ней —
        авторство записей в журнале изменений.
        """
        person = Person(full_name="Каримов К.")
        session.add(person)
        await session.flush()

        user = User(
            email="karimov@orbita.local",
            full_name="Каримов К.",
            role=Role.ASSISTANT,
            person_id=person.id,
        )
        session.add(user)
        await session.flush()

        await session.delete(person)
        await session.flush()
        await session.refresh(user)

        assert user.person_id is None, "ссылка обнуляется, но учётная запись остаётся"

    async def test_deactivated_user_stays_in_the_records(self, session: AsyncSession) -> None:
        """Отключение — не удаление: авторство прошлых записей должно сохраниться."""
        user = User(
            email="left@orbita.local",
            full_name="Ушедший",
            role=Role.ASSISTANT,
            is_active=False,
        )
        session.add(user)
        await session.flush()

        found = await session.scalar(select(User).where(User.email == "left@orbita.local"))

        assert found is not None
        assert found.is_active is False

    async def test_defaults_match_the_agency(self, session: AsyncSession) -> None:
        user = User(email="d@orbita.local", full_name="По умолчанию", role=Role.LEADER)
        session.add(user)
        await session.flush()
        await session.refresh(user)

        assert user.locale == "ru"
        assert user.timezone == "Asia/Tashkent"
        assert user.is_active is True


class TestRoles:
    def test_only_the_assistant_writes(self) -> None:
        assert Role.ASSISTANT.can_write is True
        assert Role.LEADER.can_write is False

    def test_there_are_exactly_two_roles(self) -> None:
        """Третья роль означает возврат к разграничению доступа (ADR-0003, отменён).

        Возвращаться к нему нужно до подключения третьего пользователя, а не после, —
        поэтому проверка стоит здесь, а не в списке пожеланий.
        """
        assert {str(role) for role in Role} == {"assistant", "leader"}


class TestStaffDirectory:
    async def test_staff_are_not_users(self, session: AsyncSession) -> None:
        """Появление сотрудника не заводит пользователя.

        Если бы заводило, в системе на двоих оказались бы десятки учётных записей,
        которыми никто не пользуется, — и права, которые никто не проверяет.
        """
        users_before = await session.scalar(select(func.count()).select_from(User))

        session.add(Person(full_name="Рахимов А.", position="Начальник управления"))
        await session.flush()

        assert await session.scalar(select(func.count()).select_from(Person)) == 1
        assert await session.scalar(select(func.count()).select_from(User)) == users_before

    async def test_same_person_may_repeat_by_name(self, session: AsyncSession) -> None:
        """Однофамильцы существуют: ФИО не уникально, в отличие от адреса пользователя."""
        session.add_all([Person(full_name="Каримов К."), Person(full_name="Каримов К.")])
        await session.flush()

        assert await session.scalar(select(func.count()).select_from(Person)) == 2


class TestStaffDirectoryIsReadable:
    """Выдача списка сотрудников наружу интерфейса (ORB-020).

    Список нужен фильтрам базы задач: «чьё» и «с кого спрашивать» (ТЗ 6.2). Пока его не
    было, оба фильтра было нечем наполнить — и это обнаружилось не при чтении плана, а
    при сборке экрана.
    """

    @staticmethod
    async def names(api: AsyncClient, **params: str | int | bool) -> list[str]:
        response = await api.get("/api/v1/people", params=params)
        assert response.status_code == 200, response.text
        return [item["full_name"] for item in response.json()]

    async def test_staff_come_back_ordered_by_name(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Порядок задаёт сервер.

        Выпадающий список сортируется один раз здесь, а не в каждом месте, где он
        показан: расходящийся порядок в двух фильтрах на одном экране читается как сбой.
        """
        session.add_all(
            [
                Person(full_name="Юсупов Ю."),
                Person(full_name="Абдуллаев А."),
                Person(full_name="Мирзаев М."),
            ]
        )
        await session.flush()

        assert await self.names(assistant_api) == [
            "Абдуллаев А.",
            "Мирзаев М.",
            "Юсупов Ю.",
        ]

    async def test_a_dismissed_employee_is_hidden_from_new_assignments(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        session.add_all(
            [
                Person(full_name="Действующий Д."),
                Person(full_name="Уволенный У.", is_active=False),
            ]
        )
        await session.flush()

        assert await self.names(assistant_api) == ["Действующий Д."]

    async def test_a_dismissed_employee_is_still_reachable_on_request(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Иначе из старой записи пропал бы тот, на кого её когда-то завели.

        Задача, выданная уволившемуся, никуда не делась: её видно на экране, и фильтр
        «чьи задачи» обязан суметь его назвать. Отключение — не удаление.
        """
        session.add(Person(full_name="Уволенный У.", is_active=False))
        await session.flush()

        assert await self.names(assistant_api, active_only=False) == ["Уволенный У."]

    async def test_search_matches_a_part_of_the_name_in_any_case(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Человек набирает фамилию как помнит, а не как она записана."""
        session.add_all([Person(full_name="Каримов Кабул"), Person(full_name="Рахимов Р.")])
        await session.flush()

        assert await self.names(assistant_api, search="КАРИМ") == ["Каримов Кабул"]
        assert await self.names(assistant_api, search="  каримов  ") == ["Каримов Кабул"]
        assert await self.names(assistant_api, search="нет такого") == []

    async def test_the_leader_reads_the_directory_too(
        self, leader_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Граница проходит по периметру системы, а не между пользователями (ADR-0011).

        Руководитель не пишет, но видит всё: список сотрудников ему нужен ровно так же —
        отфильтровать задачи по исполнителю.
        """
        session.add(Person(full_name="Рахимов Р."))
        await session.flush()

        assert await self.names(leader_api) == ["Рахимов Р."]
