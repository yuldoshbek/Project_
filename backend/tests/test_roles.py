"""Две роли без входа (ADR-0011, ADR-0026).

Входа в системе нет с 18.09.2026, и этот набор переписан под новое обещание. Роль больше
не охраняет данные — охраной занимается периметр. Она делает две другие вещи, и обе
проверяются здесь.

Первое: роль подписывает действие. Руководитель не может изменить ничего, кроме решения
по проекту, и отказ приходит кодом 403 — не потому, что он «не вошёл», а потому, что он
смотрит, а не вносит. Это защита от промаха, а не от злоумышленника, и говорить о ней
надо честно: заголовок подделывается тривиально.

Второе, зеркальное и более важное: **ни один маршрут не требует входа**. После снятия
авторизации легко оставить забытую зависимость, которая отвечает 401 на пустом месте, —
и тогда часть системы окажется недоступна без единого сообщения о причине.

Отдельно проверяется, что от снятых механизмов — разграничения по проектам и самого
входа — не осталось следов в коде. Мёртвый механизм опаснее отсутствующего: его однажды
примут за работающий и начнут на него опираться.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from httpx import AsyncClient

from app.api.router import API_PREFIX
from app.api.security import ACTOR_HEADER, Assistant
from app.domain.people import Role

pytestmark = pytest.mark.infra

SAMPLE_ID = "00000000-0000-0000-0000-000000000000"

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


class TestWriteIsAssistantOnly:
    async def test_assistant_may_write(self, assistant_api: AsyncClient) -> None:
        response = await assistant_api.post("/api/v1/probe/write")
        assert response.status_code == 204

    async def test_leader_may_not_write(self, leader_api: AsyncClient) -> None:
        response = await leader_api.post("/api/v1/probe/write")
        assert response.status_code == 403

    async def test_refusal_explains_the_mode_not_the_session(self, leader_api: AsyncClient) -> None:
        """Отказ говорит про режим, а не про вход.

        Раньше здесь проверялось, что 403 не подменяется на 401 и интерфейс не уводит
        руководителя на экран входа. Экрана входа больше нет, и обещание стало проще:
        сообщение объясняет, что делать — переключить режим, — а не намекает на
        несуществующую сессию.
        """
        response = await leader_api.post("/api/v1/probe/write")
        assert response.status_code == 403
        detail = response.json()["detail"].lower()
        assert "вход" not in detail
        assert "помощник" in detail


class TestRoleComesFromTheHeader:
    """Роль приезжает заголовком, и сервер верит ему на слово (ADR-0026)."""

    async def test_no_header_means_assistant(self, api: AsyncClient) -> None:
        """Без заголовка действует помощник.

        Умолчание в его пользу выбрано намеренно: данные вносит он. Приняв за
        руководителя того, кто им не представился, мы приписали бы ему чужие правки.
        """
        response = await api.post("/api/v1/probe/write")
        assert response.status_code == 204

    async def test_unknown_role_is_not_an_error(self, api: AsyncClient) -> None:
        """Опечатка в заголовке не роняет запрос: заголовок не охраняет вход.

        Отказ на непонятное значение воспроизвёл бы вход под другим именем — ровно то,
        что ADR-0026 снимает.

        Значение латиницей намеренно: в заголовки HTTP кириллица не проходит, и тест с
        русским словом проверял бы кодировку httpx, а не наше правило.
        """
        response = await api.post("/api/v1/probe/write", headers={ACTOR_HEADER: "director"})
        assert response.status_code == 204

    async def test_leader_header_actually_switches_the_role(self, api: AsyncClient) -> None:
        response = await api.post("/api/v1/probe/write", headers={ACTOR_HEADER: Role.LEADER.value})
        assert response.status_code == 403

    async def test_case_and_spaces_do_not_matter(self, api: AsyncClient) -> None:
        """Заголовок пишет человек и переписывает клиент — форма не должна решать.

        Роль, которая срабатывает только при точном совпадении регистра, даёт самый
        неприятный вид ошибки: всё работает, но действия подписаны не тем.
        """
        response = await api.post("/api/v1/probe/write", headers={ACTOR_HEADER: "  LEADER  "})
        assert response.status_code == 403


class TestNothingAsksForALogin:
    """Зеркало прежней проверки «каждый маршрут требует сессию».

    Растёт вместе с системой сама: новый роутер попадает сюда в тот момент, когда его
    подключают, а не когда о нём вспомнят.
    """

    def test_the_check_has_something_to_check(self, app: FastAPI) -> None:
        """Страховка от пустого обхода: без маршрутов проверка ничего не значит."""
        assert len(api_endpoints(app)) > 10

    async def test_no_route_answers_401(self, app: FastAPI, api: AsyncClient) -> None:
        asking_for_login: list[str] = []
        for method, path in api_endpoints(app):
            response = await api.request(method, path.replace("{id}", SAMPLE_ID))
            if response.status_code == 401:
                asking_for_login.append(f"{method} {path}")

        assert not asking_for_login, (
            "входа в системе нет (ADR-0026), но эти маршруты всё ещё требуют его:\n"
            + "\n".join(asking_for_login)
        )

    def test_the_login_endpoints_are_gone(self, app: FastAPI) -> None:
        """Маршрутов входа не осталось даже отключёнными."""
        paths = {path for _, path in api_endpoints(app)}
        assert not [path for path in paths if "/auth/" in path]


class TestNoTracesOfRemovedMechanisms:
    """Разграничение по проектам (COUNCIL-0002) и вход (ADR-0026) сняты."""

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
