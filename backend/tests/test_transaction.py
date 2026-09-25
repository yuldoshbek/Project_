"""Граница транзакции запроса.

Проверяется одно обещание: **клиент узнаёт об успехе только после того, как транзакция
закрыта.** Пока это было не так, система лгала — говорила «создано» о записи, которой для
следующего запроса ещё не существовало. Симптомы выглядели как три разные болезни:
пропадала каждая вторая задача, заведённая подряд; отметка пункта чек-листа отвечала «не
найдено» для пункта, созданного мгновение назад; повторный ввод тега давал 500.

Проверка написана на пробном маршруте с поддельной сессией, а не на настоящих данных.
Причина в том, что настоящая сессия в тестах подменена общей на весь тест: фиксировать её
посреди проверки значило бы ломать откат между тестами. Поддельная сессия отвечает на
единственный вопрос, который здесь важен, — **звали ли `commit` и когда**.

Отдельно проверяется соглашение: каждый роутер API заведён через `transactional_router`.
Роутер, созданный мимо него, тихо возвращается к прежнему поведению — работает и обещает
записанное раньше, чем оно записано.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.api import routes
from app.api.transaction import SESSION_STATE_ATTRIBUTE, CommitOnSuccess, transactional_router
from app.domain.errors import NotFoundError


class SpySession:
    """Сессия, которая только запоминает, что с ней делали."""

    def __init__(self) -> None:
        self.events: list[str] = []

    async def commit(self) -> None:
        self.events.append("commit")

    async def rollback(self) -> None:
        self.events.append("rollback")


@pytest.fixture
def spy() -> SpySession:
    return SpySession()


@pytest.fixture
def probe_app(spy: SpySession) -> FastAPI:
    """Приложение из одного роутера: обычный путь, отказ и падение."""
    router = transactional_router()

    @router.get("/probe/ok")
    async def ok(request: Request) -> dict[str, str]:
        setattr(request.state, SESSION_STATE_ATTRIBUTE, spy)
        spy.events.append("обработчик")
        return {"status": "ok"}

    @router.get("/probe/refused")
    async def refused(request: Request) -> dict[str, str]:
        setattr(request.state, SESSION_STATE_ATTRIBUTE, spy)
        raise NotFoundError("Запись не найдена")

    @router.get("/probe/broken")
    async def broken(request: Request) -> dict[str, str]:
        setattr(request.state, SESSION_STATE_ATTRIBUTE, spy)
        raise RuntimeError("что-то сломалось")

    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
async def probe(probe_app: FastAPI) -> Any:
    transport = ASGITransport(app=probe_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


class TestCommitPrecedesTheAnswer:
    async def test_a_successful_request_is_committed_before_it_answers(
        self, probe: AsyncClient, spy: SpySession
    ) -> None:
        """Порядок важнее самого факта: фиксация обязана случиться до ответа.

        Раньше она случалась после — и следующий запрос клиента приходил в базу раньше,
        чем туда доходила предыдущая запись.
        """
        response = await probe.get("/probe/ok")

        assert response.status_code == 200
        assert spy.events == ["обработчик", "commit"]

    async def test_a_refused_request_is_not_committed(
        self, probe: AsyncClient, spy: SpySession
    ) -> None:
        """Отказ по правилу предметной области не закрепляет ничего.

        Иначе половина изменения, сделанного до отказа, осталась бы в базе.
        """
        await probe.get("/probe/refused")

        assert "commit" not in spy.events

    async def test_a_broken_request_is_not_committed(
        self, probe: AsyncClient, spy: SpySession
    ) -> None:
        await probe.get("/probe/broken")

        assert "commit" not in spy.events

    async def test_a_request_without_a_session_answers_as_usual(self, probe_app: FastAPI) -> None:
        """Не каждый маршрут работает с базой, и такой не должен падать на фиксации."""
        router = transactional_router()

        @router.get("/probe/sessionless")
        async def sessionless() -> dict[str, str]:
            return {"status": "ok"}

        probe_app.include_router(router)
        transport = ASGITransport(app=probe_app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/probe/sessionless")

        assert response.status_code == 200


class TestEveryRouterHasTheBoundary:
    """Соглашение, которое иначе нарушит первый же новый роутер.

    Обходом пакета, а не списком имён: список забывают пополнить, а модуль, добавленный в
    `app/api/routes`, попадёт сюда сам. И не обходом `api_router.routes`: устройство этого
    списка у FastAPI менялось — в 0.141 включённый роутер лежит там одним непрозрачным
    объектом, и обход по нему однажды молча перестал бы что-либо находить.
    """

    @staticmethod
    def routers() -> list[tuple[str, APIRouter]]:
        found: list[tuple[str, APIRouter]] = []
        for info in pkgutil.iter_modules(routes.__path__):
            module = importlib.import_module(f"{routes.__name__}.{info.name}")
            router = getattr(module, "router", None)
            if isinstance(router, APIRouter):
                found.append((info.name, router))
        return found

    def test_every_router_commits_before_answering(self) -> None:
        outsiders = [
            name
            for name, router in self.routers()
            if not issubclass(router.route_class, CommitOnSuccess)
        ]

        assert not outsiders, (
            "роутеры заведены мимо transactional_router и фиксируют транзакцию "
            f"после ответа: {outsiders}"
        )

    def test_the_check_has_something_to_check(self) -> None:
        """Страховка от тихого вырождения: пустой обход прошёл бы молча."""
        names = {name for name, _ in self.routers()}

        # Известные модули, а не порог по числу: роутеров становится больше с каждым экраном
        # блока, и порог «не меньше N» пришлось бы переписывать вместе с ними.
        expected = {"access", "dictionaries", "health", "internal"}
        assert expected <= names, f"обход не нашёл известные роутеры, он сломан: {names}"
