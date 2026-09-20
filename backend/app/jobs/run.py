"""Запуск задачи из командной строки: `make job n=morning-summary`.

Нужно в двух случаях: проверить задачу на машине разработчика и выполнить её руками, когда
расписание недоступно. Та же функция, та же идемпотентность — отличается только способ
позвать.

    python -m app.jobs.run morning-summary
    python -m app.jobs.run deadline-check --force   # прогнать повторно за тот же период
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.jobs import all_jobs, run_job
from app.repos.database import dispose_database, init_database, session_scope
from app.settings import get_settings


async def main(name: str, *, force: bool) -> int:
    settings = get_settings()
    init_database(settings)
    try:
        async for session in session_scope():
            outcome = await run_job(
                session,
                name,
                timezone=settings.timezone,
                force=force,
            )
        print(
            json.dumps(
                {
                    "job": outcome.name,
                    "period": outcome.period,
                    "status": outcome.status,
                    "skipped": outcome.skipped,
                    "result": outcome.result,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        await dispose_database()
    return 0


def cli() -> int:
    parser = argparse.ArgumentParser(description="Выполнить задачу по расписанию")
    parser.add_argument("name", nargs="?", help="имя задачи")
    parser.add_argument(
        "--force",
        action="store_true",
        help="выполнить повторно за тот же период (для разработки и разбора)",
    )
    args = parser.parse_args()

    jobs = all_jobs()
    if not args.name:
        print("Задачи:")
        for job in jobs.values():
            print(f"  {job.name:18} {job.title}")
        return 1

    if args.name not in jobs:
        print(f"нет задачи «{args.name}». Есть: {', '.join(sorted(jobs))}", file=sys.stderr)
        return 1

    return asyncio.run(main(args.name, force=args.force))


if __name__ == "__main__":
    raise SystemExit(cli())
