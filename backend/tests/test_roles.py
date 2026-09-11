"""Две роли вместо матрицы прав (ORB-053, ADR-0011).

Проверяется не «работает ли зависимость», а два обещания, которые дороже всего нарушить.

Первое: руководитель не может изменить ничего, кроме решения по проекту, и отказ приходит
кодом 403 — сессия у него действует, и уводить его на экран входа за попытку записи
нельзя. Второе: роль берётся из базы, а не из запроса и не из подписанного утверждения в
токене. Второе важнее первого: охранник, которого можно уговорить параметром запроса, —
это не охранник.

Отдельно проверяется, что от снятого разграничения по проектам не осталось следов в коде
(COUNCIL-0002). Мёртвая матрица прав опаснее отсутствующей: её однажды примут за
работающую и начнут на неё опираться.

И, наконец, что каждый маршрут вообще требует сессию. Это единственная проверка, которая
растёт вместе с системой сама: новый роутер попадает в неё в тот момент, когда его
подключают, а не когда о нём вспомнят.
"""

from __future__ import annotations

import re
from pathlib import Path

import jwt
import pytest
from fastapi import APIRouter, FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.router import API_PREFIX
from app.api.security import Assistant, create_access_token
from app.domain.people import Role
from app.repos.models import User
from app.settings import Settings

pytestmark = pytest.mark.infra

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
    app.include_router(probe, prefix="/api/v1")


class TestWriteIsAssistantOnly:
    async def test_assistant_may_write(self, assistant_api: AsyncClient) -> None:
        response = await assistant_api.post("/api/v1/probe/write")

        assert response.status_code == 204

    async def test_leader_may_not_write(self, leader_api: AsyncClient) -> None:
        response = await leader_api.post("/api/v1/probe/write")

        assert response.status_code == 403
        assert response.json()["type"].endswith("permission-denied")

    async def test_refusal_to_leader_is_not_a_session_problem(
        self, leader_api: AsyncClient
    ) -> None:
        """403, а не 401, и это не формальность.

        Интерфейс по 401 уводит на экран входа. Руководитель, которому отказали в записи,
        вошёл и остаётся в системе: увести его на вход означало бы сказать, что он не тот,
        за кого себя выдаёт, — вместо «это действие не ваше».
        """
        refused = await leader_api.post("/api/v1/probe/write")
        readable = await leader_api.get("/api/v1/me")

        assert refused.status_code == 403
        assert readable.status_code == 200, "отказ в записи не должен закрывать чтение"


class TestRoleComesFromTheDatabase:
    async def test_role_claim_in_the_token_does_not_grant_anything(
        self, api: AsyncClient, session: AsyncSession, settings: Settings
    ) -> None:
        """Токен подписан нами, но утверждение о роли в нём — не пропуск.

        Роль читается из базы на каждом запросе. Иначе смена роли или отключение
        пользователя действовали бы только после истечения токена, а украденный токен
        сохранял бы полномочия, которых у владельца уже нет.
        """
        leader = await session.scalar(select(User).where(User.role == Role.LEADER))
        assert leader is not None
        leader.must_change_password = False
        await session.flush()

        forged = jwt.encode(
            {
                "sub": str(leader.id),
                # Подписано нашим ключом и формально безупречно — и всё равно ничего не даёт.
                "role": Role.ASSISTANT.value,
                "typ": "access",
            },
            settings.secret_key.get_secret_value(),
            algorithm="HS256",
        )

        response = await api.post(
            "/api/v1/probe/write",
            headers={"Authorization": f"Bearer {forged}"},
        )

        assert response.status_code == 403

    async def test_role_cannot_be_supplied_by_the_request(self, leader_api: AsyncClient) -> None:
        """Ни параметром запроса, ни телом."""
        by_query = await leader_api.post("/api/v1/probe/write?role=assistant")
        by_body = await leader_api.post("/api/v1/probe/write", json={"role": "assistant"})

        assert by_query.status_code == 403
        assert by_body.status_code == 403

    async def test_temporary_password_is_checked_before_the_role(
        self, api: AsyncClient, session: AsyncSession, settings: Settings
    ) -> None:
        """Помощнику с невыданным паролем отказывают по паролю, а не по роли.

        Порядок важен для сообщения: «смените временный пароль» ведёт к действию,
        «изменение данных доступно только помощнику» помощника собьёт с толку.
        """
        assistant = await session.scalar(select(User).where(User.role == Role.ASSISTANT))
        assert assistant is not None
        assistant.must_change_password = True
        await session.flush()

        response = await api.post(
            "/api/v1/probe/write",
            headers={"Authorization": f"Bearer {create_access_token(assistant, settings)}"},
        )

        assert response.status_code == 403
        assert response.json()["type"].endswith("password-change-required")


class TestNoTracesOfProjectLevelAccess:
    """Разграничение по проектам снято (COUNCIL-0002). Следов остаться не должно."""

    # Имена из снятого ORB-008. Строка ищется как есть, регистр не учитывается.
    FORBIDDEN = ("project_members", "visible_projects", "test_rbac_no_leaks")

    SCANNED = (
        ("backend/app", (".py",)),
        ("backend/alembic", (".py",)),
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

        assert not found, (
            "разграничение по проектам снято, но в коде остались его следы:\n" + "\n".join(found)
        )


# Маршруты, которые обязаны отвечать без сессии: ими её получают и ею же заканчивают.
# Список закрытый и короткий — всё, что в него попадает, попадает осознанно.
PUBLIC_PATHS = frozenset(
    {
        f"{API_PREFIX}/auth/login",
        f"{API_PREFIX}/auth/refresh",
        f"{API_PREFIX}/auth/logout",
    }
)

SAMPLE_ID = "00000000-0000-0000-0000-000000000000"


def api_endpoints(application: FastAPI) -> list[tuple[str, str]]:
    """Метод и путь каждого маршрута API — по описанию схемы.

    Схема, а не обход `app.routes`: внутреннее устройство списка маршрутов у FastAPI
    менялось (в 0.141 включённый роутер лежит там одним непрозрачным объектом), и обход
    по нему однажды молча перестал бы что-либо находить. Схема — это то, что FastAPI
    обещает наружу; по ней же собирается клиент интерфейса.
    """
    schema = application.openapi()
    return sorted(
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        for method in operations
        if path.startswith(API_PREFIX)
    )


class TestEveryEndpointNeedsASession:
    """Ни один маршрут не отвечает без сессии.

    Проверка написана обходом приложения, а не перечислением путей, потому что забывают
    именно новые роутеры: зависимость ставится на роутер один раз, и её отсутствие ничем
    себя не проявляет — эндпоинт работает, просто работает для всех. Отсюда же выбор
    проверять живым запросом, а не осмотром зависимостей: осмотр видит, что зависимость
    объявлена, но не то, что она срабатывает раньше разбора запроса.
    """

    def test_the_check_has_something_to_check(self, app: FastAPI) -> None:
        """Страховка от тихого вырождения: пустой обход прошёл бы молча."""
        guarded = [route for route in api_endpoints(app) if route[1] not in PUBLIC_PATHS]

        assert len(guarded) > 10, f"маршрутов почти не нашлось, обход сломан: {guarded}"

    async def test_no_route_answers_without_a_session(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        open_routes = []
        for method, path in api_endpoints(app):
            if path in PUBLIC_PATHS:
                continue
            response = await client.request(method, re.sub(r"\{[^}]+\}", SAMPLE_ID, path))
            if response.status_code != 401:
                open_routes.append(f"{method} {path} → {response.status_code}")

        assert not open_routes, f"маршруты отвечают без сессии: {open_routes}"

    async def test_the_refusal_says_how_to_get_a_session(self, client: AsyncClient) -> None:
        """401 без `WWW-Authenticate` — это отказ, из которого не следует, что делать."""
        response = await client.get(f"{API_PREFIX}/tasks")

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
