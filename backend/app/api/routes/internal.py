"""Служебный вход для расписания.

Сюда обращается GitHub Actions по расписанию (ADR-0035). Ни интерфейс, ни человек этим
путём не пользуются, поэтому:

- путь не начинается с `/api` — интерфейс проксирует только его, и адрес задач через сайт
  недоступен вовсе;
- вход закрыт секретом в заголовке, а не сессией: у расписания нет и не должно быть личной
  ссылки;
- сравнение секрета идёт за постоянное время: иначе по времени ответа его можно подобрать.

Ответ всегда говорит, что произошло: выполнено, уже было сделано или задача не найдена.
«Уже было сделано» — не ошибка, а нормальный исход второго вызова.
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import Header
from pydantic import BaseModel

from app.api.deps import SessionDep, SettingsDep
from app.api.transaction import transactional_router
from app.domain.errors import NotAuthenticatedError
from app.jobs import run_job

router = transactional_router(prefix="/internal", tags=["служебные"], include_in_schema=False)

# Имя заголовка, а не сам секрет: линтер видит слово «secret» и подозревает худшее.
JOBS_SECRET_HEADER = "X-Orbita-Jobs-Secret"  # noqa: S105


class JobRunResponse(BaseModel):
    status: str
    job: str
    period: str
    skipped: bool
    result: dict[str, Any]


@router.post("/jobs/{name}", response_model=JobRunResponse, summary="Выполнить задачу")
async def run(
    name: str,
    session: SessionDep,
    settings: SettingsDep,
    x_orbita_jobs_secret: str = Header(default=""),
) -> JobRunResponse:
    """Выполняет задачу один раз за её период.

    Заголовок с секретом обязателен. Ошибка при его отсутствии — 401, а не 403: тот, кто
    пришёл без секрета, не «не имеет права», а не назвался.
    """
    expected = settings.jobs_secret.get_secret_value()
    # Сравниваются байты, а не строки: `compare_digest` на строках с неascii-символами
    # не сравнивает, а падает — и вместо честного отказа получается 500.
    if not hmac.compare_digest(x_orbita_jobs_secret.encode("utf-8"), expected.encode("utf-8")):
        raise NotAuthenticatedError("Неверный секрет задачи")

    # Часовой пояс — из настроек системы, как у командной строки (`app.jobs.run`): период
    # «сутки» у расписания и у ручного запуска обязан быть одним и тем же, иначе вызов
    # руками и вызов по расписанию разойдутся в том, какой сегодня день.
    outcome = await run_job(session, name, timezone=settings.timezone)
    return JobRunResponse(
        status=outcome.status,
        job=outcome.name,
        period=outcome.period,
        skipped=outcome.skipped,
        result=outcome.result,
    )
