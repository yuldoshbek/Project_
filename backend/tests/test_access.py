"""Доступ по личной ссылке (ADR-0029) и две роли (ADR-0011).

Этот набор проверяет единственное, что отделяет систему от чужой вкладки. Пароля и экрана
входа нет, поэтому ошибка здесь не выглядит как ошибка: система просто работает — для
всех.

Три обещания:

1. **Без сессии API не отдаёт ничего.** Проверка идёт по схеме, то есть по всем маршрутам
   сразу: новый роутер попадает под неё в момент подключения, а не когда о нём вспомнят.
2. **Ссылка открывает сессию, перевыпуск её закрывает.** Тот, кому переслали прежнюю
   ссылку, теряет доступ в тот же момент.
3. **Запись — дело помощника.** Руководитель смотрит и решает; отказ говорит про режим, а
   не про вход.

Отдельно проверяется, что от снятых механизмов — разграничения по проектам, пароля и
заголовка роли — не осталось следов. Мёртвый механизм опаснее отсутствующего: его однажды
примут за работающий.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.router import API_PREFIX
from app.api.security import Assistant
from app.domain.access import SESSION_COOKIE, fingerprint, needs_touch
from app.domain.errors import RuleViolationError
from app.domain.people import Role
from app.repos.models import AccessLink, User
from app.repos.models import Session as SessionRecord
from app.services import access
from app.settings import Settings
from tests.conftest import open_session_for

pytestmark = pytest.mark.infra

SAMPLE_ID = "00000000-0000-0000-0000-000000000000"

# Любой параметр пути — `{id}`, `{project_type_id}` и те, что придут с экранами блока.
# Подстановка по одному имени пропускала бы новые маршруты мимо проверки молча.
PATH_PARAMETER = re.compile(r"\{[^}]+\}")

# Точка, в которой проверяется охранник. Пробный маршрут, а не настоящий: он проверяет
# зависимость насквозь — через маршрутизацию, обработчик ошибок и формат ответа, — и при
# этом не зависит от того, что именно умеет делать конкретный раздел сегодня.
probe = APIRouter()


@probe.post("/probe/write", status_code=204, summary="Пробная запись")
async def probe_write(user: Assistant) -> None:
    """Ничего не делает. Нужен только для проверки охранника."""
    return None


@pytest.fixture(autouse=True)
def mount_probe(app: FastAPI) -> None:
    """Подключается автоматически и потому раньше клиентских фикстур этого модуля."""
    app.include_router(probe, prefix=API_PREFIX)


def api_endpoints(application: FastAPI) -> list[tuple[str, str]]:
    """Метод и путь каждого маршрута API — по описанию схемы.

    Схема, а не обход `app.routes`: внутреннее устройство списка маршрутов у FastAPI
    менялось, и обход по нему однажды молча перестал бы что-либо находить. Схема — это то,
    что FastAPI обещает наружу; по ней же собирается клиент интерфейса.
    """
    schema = application.openapi()
    return sorted(
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        for method in operations
        if path.startswith(API_PREFIX)
    )


class TestSessionIsRequired:
    def test_the_check_has_something_to_check(self, app: FastAPI) -> None:
        """Страховка от пустого обхода: без маршрутов проверка ничего не значит.

        Проверяется присутствие известного маршрута данных, а не их число: число меняется
        с каждым экраном блока, и порог «больше N» пришлось бы переписывать вместе с ним.
        """
        endpoints = api_endpoints(app)
        assert ("GET", f"{API_PREFIX}/dictionaries") in endpoints
        assert ("POST", f"{API_PREFIX}/probe/write") in endpoints

    async def test_every_data_route_refuses_without_a_session(
        self, app: FastAPI, api: AsyncClient
    ) -> None:
        """Ни один маршрут данных не отвечает без личной ссылки.

        Забытая проверка на отдельном пути не видна на ревью, а открывает всё, что этот
        путь отдаёт, — включая поручения Администрации Президента.
        """
        answered: list[str] = []
        for method, path in api_endpoints(app):
            response = await api.request(method, PATH_PARAMETER.sub(SAMPLE_ID, path))
            if response.status_code != 401:
                answered.append(f"{method} {path} → {response.status_code}")

        assert not answered, "эти маршруты отвечают без сессии:\n" + "\n".join(answered)

    async def test_refusal_says_what_to_do(self, api: AsyncClient) -> None:
        response = await api.get(f"{API_PREFIX}/dictionaries")

        assert response.status_code == 401
        assert "ссылк" in response.json()["detail"].lower()


class TestGivenToken:
    """Первая ссылка в облаке — по токену, который заказчик кладёт в секрет.

    Иначе её пришлось бы печатать в журнал прогона, а журналы публичного репозитория
    читает кто угодно.
    """

    async def test_given_token_opens_a_session(
        self, api: AsyncClient, session: AsyncSession, settings: Settings
    ) -> None:
        assistant = await session.scalar(select(User).where(User.role == Role.ASSISTANT.value))
        assert assistant is not None
        chosen = "z" * 20 + "-" + "A1_" * 8

        issued = await access.issue_link(
            session,
            user=assistant,
            secret=settings.session_secret.get_secret_value(),
            base_url="http://test",
            now=datetime.now(UTC),
            token=chosen,
        )

        assert issued.url.endswith(f"/api/access/{chosen}")
        response = await api.get(f"/api/access/{chosen}", follow_redirects=False)
        assert response.status_code == 303

    @pytest.mark.parametrize("weak", ["short", "с кириллицей" * 5, "a" * 42, "a" * 50 + "/"])
    async def test_weak_given_token_is_refused(
        self, session: AsyncSession, settings: Settings, weak: str
    ) -> None:
        """Заданный токен не слабее выпускаемого: 43 символа из алфавита адреса."""
        assistant = await session.scalar(select(User).where(User.role == Role.ASSISTANT.value))
        assert assistant is not None

        with pytest.raises(RuleViolationError):
            await access.issue_link(
                session,
                user=assistant,
                secret=settings.session_secret.get_secret_value(),
                base_url="http://test",
                now=datetime.now(UTC),
                token=weak,
            )


class TestOpeningByLink:
    async def test_link_opens_a_session(
        self, app: FastAPI, api: AsyncClient, session: AsyncSession, settings: Settings
    ) -> None:
        """Переход по ссылке ставит cookie, и дальше система просто работает."""
        assistant = await session.scalar(select(User).where(User.role == Role.ASSISTANT.value))
        assert assistant is not None
        issued = await access.issue_link(
            session,
            user=assistant,
            secret=settings.session_secret.get_secret_value(),
            base_url="http://test",
            now=datetime.now(UTC),
        )
        token = issued.url.rsplit("/", 1)[-1]

        response = await api.get(f"/api/access/{token}", follow_redirects=False)

        assert response.status_code == 303
        assert SESSION_COOKIE in response.cookies
        cookie_header = response.headers["set-cookie"]
        assert "HttpOnly" in cookie_header
        assert "Secure" in cookie_header
        assert "SameSite=lax" in cookie_header or "SameSite=Lax" in cookie_header

    async def test_the_session_works_after_the_redirect(
        self, api: AsyncClient, session: AsyncSession, settings: Settings
    ) -> None:
        assistant = await session.scalar(select(User).where(User.role == Role.ASSISTANT.value))
        assert assistant is not None
        issued = await access.issue_link(
            session,
            user=assistant,
            secret=settings.session_secret.get_secret_value(),
            base_url="http://test",
            now=datetime.now(UTC),
        )
        token = issued.url.rsplit("/", 1)[-1]
        await api.get(f"/api/access/{token}", follow_redirects=False)

        response = await api.get("/api/me")

        assert response.status_code == 200
        assert response.json()["role"] == Role.ASSISTANT.value
        assert response.json()["can_write"] is True

    async def test_unknown_link_is_a_plain_not_found(self, api: AsyncClient) -> None:
        """Ответ не объясняет, чем ссылка не подошла: подсказка помогала бы подбору."""
        response = await api.get("/api/access/явно-не-тот-токен", follow_redirects=False)

        assert response.status_code == 404

    async def test_the_token_is_not_stored(self, session: AsyncSession, settings: Settings) -> None:
        """В базе лежит отпечаток. Копия базы без ключа приложения входа не даёт."""
        leader = await session.scalar(select(User).where(User.role == Role.LEADER.value))
        assert leader is not None
        issued = await access.issue_link(
            session,
            user=leader,
            secret=settings.session_secret.get_secret_value(),
            base_url="http://test",
            now=datetime.now(UTC),
        )
        token = issued.url.rsplit("/", 1)[-1]

        link = await session.scalar(select(AccessLink).where(AccessLink.user_id == leader.id))
        assert link is not None
        assert token not in link.token_fingerprint
        assert link.token_fingerprint == fingerprint(
            token, settings.session_secret.get_secret_value()
        )


class TestReissue:
    async def test_reissue_closes_the_previous_session(
        self, app: FastAPI, api: AsyncClient, session: AsyncSession, settings: Settings
    ) -> None:
        """Пересланная ссылка перестаёт работать в тот же момент — в этом смысл кнопки."""
        token = await open_session_for(session, settings, Role.LEADER)
        api.cookies.set(SESSION_COOKIE, token)
        assert (await api.get("/api/me")).status_code == 200

        leader = await session.scalar(select(User).where(User.role == Role.LEADER.value))
        assert leader is not None
        await access.issue_link(
            session,
            user=leader,
            secret=settings.session_secret.get_secret_value(),
            base_url="http://test",
            now=datetime.now(UTC),
        )

        assert (await api.get("/api/me")).status_code == 401

    async def test_only_the_assistant_reissues(self, leader_api: AsyncClient) -> None:
        """Ссылками занимается помощник: он отвечает за доступы и отправляет ссылку."""
        response = await leader_api.post("/api/access/links/leader")

        assert response.status_code == 403

    async def test_assistant_sees_the_new_link_once(self, assistant_api: AsyncClient) -> None:
        response = await assistant_api.post("/api/access/links/leader")

        assert response.status_code == 200
        assert response.json()["url"].startswith("http")
        assert "/api/access/" in response.json()["url"]


class TestSessionLifetime:
    async def test_expired_session_is_refused(
        self, api: AsyncClient, session: AsyncSession, settings: Settings
    ) -> None:
        token = await open_session_for(session, settings, Role.ASSISTANT)
        record = await session.scalar(
            select(SessionRecord).where(
                SessionRecord.token_fingerprint
                == fingerprint(token, settings.session_secret.get_secret_value())
            )
        )
        assert record is not None
        record.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await session.flush()

        api.cookies.set(SESSION_COOKIE, token)
        assert (await api.get("/api/me")).status_code == 401

    def test_touch_is_not_written_on_every_request(self) -> None:
        """Интерфейс опрашивает API раз в пятнадцать секунд (ADR-0034).

        Запись отметки на каждом запросе — это четыре записи в минуту ради строки,
        которую смотрят раз в месяц.
        """
        now = datetime.now(UTC)
        assert needs_touch(None, now) is True
        assert needs_touch(now - timedelta(seconds=15), now) is False
        assert needs_touch(now - timedelta(hours=2), now) is True


class TestWriteIsAssistantOnly:
    async def test_assistant_may_write(self, assistant_api: AsyncClient) -> None:
        response = await assistant_api.post(f"{API_PREFIX}/probe/write")
        assert response.status_code == 204

    async def test_leader_may_not_write(self, leader_api: AsyncClient) -> None:
        response = await leader_api.post(f"{API_PREFIX}/probe/write")
        assert response.status_code == 403

    async def test_refusal_explains_the_mode_not_the_session(self, leader_api: AsyncClient) -> None:
        """Отказ говорит про режим, а не про вход: у руководителя сессия есть."""
        response = await leader_api.post(f"{API_PREFIX}/probe/write")

        assert response.status_code == 403
        detail = response.json()["detail"].lower()
        assert "помощник" in detail


class TestNoTracesOfRemovedMechanisms:
    """Разграничение по проектам, пароли и заголовок роли сняты."""

    # Имена снятых механизмов. Строка ищется как есть, регистр не учитывается.
    FORBIDDEN = (
        "project_members",
        "visible_projects",
        "test_rbac_no_leaks",
        "password_hash",
        "must_change_password",
        "refresh_token",
        "create_access_token",
        "identityprovider",
        "x-orbita-actor",
        "share_externally",
    )

    SCANNED = (
        ("backend/app", (".py",)),
        ("backend/tests", (".py",)),
        ("frontend/src", (".ts", ".tsx")),
    )

    def test_removed_names_are_absent_from_the_code(self) -> None:
        root = Path(__file__).resolve().parent.parent.parent
        here = Path(__file__).resolve()
        found: list[str] = []

        for folder, suffixes in self.SCANNED:
            base = root / folder
            if not base.is_dir():
                pytest.fail(f"каталог {folder} не найден — проверка молча ничего не сканирует")
            for path in base.rglob("*"):
                if path.suffix not in suffixes or path.resolve() == here:
                    continue
                if "__pycache__" in path.parts or "node_modules" in path.parts:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace").lower()
                for name in self.FORBIDDEN:
                    if name in text:
                        found.append(f"{path.relative_to(root)}: {name}")

        assert not found, "механизм снят, но в коде остались его следы:\n" + "\n".join(found)
