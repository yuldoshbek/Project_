"""Задачи по расписанию: секрет, идемпотентность, догоняющий режим.

Главное обещание здесь — **повторный вызов не делает работу дважды**. Расписание
доставляет запуск «по возможности» (ADR-0035): может пропустить, может позвать дважды,
может позвать две функции одновременно. Ошибка в этом месте выглядит как две утренние
сводки подряд — и это самая заметная для руководителя поломка из всех дешёвых.
"""

from __future__ import annotations

import base64
import re
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.push import MAILTO_SUBJECT, PushOutcome, WebPushSender
from app.domain.clock import local_date, now_utc
from app.domain.people import Role
from app.domain.push import LAST_SUMMARY_RUN, SUMMARY_WINDOW, summary_key
from app.jobs import all_jobs, run_job
from app.jobs.registry import Job, JobContext, Release, daily_period, register
from app.push_keys import new_private_key
from app.repos.models import JobRun, Notification, PushSubscription, Setting, User
from app.settings import Settings
from tests.fakes import FakePushSender

pytestmark = pytest.mark.infra

SECRET_HEADER = "X-Orbita-Jobs-Secret"
REPO_ROOT = Path(__file__).resolve().parents[2]
TASHKENT = ZoneInfo("Asia/Tashkent")

# Ключи подписки по форме настоящих: точка P-256 и 16 байт. Подделка их не расшифровывает.
P256DH = "B" + "A" * 86
AUTH = "A" * 22


@pytest.fixture
def sender() -> FakePushSender:
    return FakePushSender()


def schedule() -> str:
    return (REPO_ROOT / ".github" / "workflows" / "jobs.yml").read_text(encoding="utf-8")


def case_lines(workflow: str) -> dict[str, str]:
    """Строки `case` в jobs.yml: строка cron → имя задачи."""
    return dict(re.findall(r"^\s*'([^']+)'\)\s*job=([a-z-]+)\s*;;", workflow, re.MULTILINE))


def cron_values(field: str, top: int) -> set[int]:
    """Значения одного поля cron: `*`, `*/10`, `1-6`, `5`, списки через запятую."""
    values: set[int] = set()
    for part in field.split(","):
        spec, _, step = part.partition("/")
        if spec == "*":
            low, high = 0, top
        elif "-" in spec:
            low, high = (int(bound) for bound in spec.split("-"))
        else:
            low = int(spec)
            high = top if step else low
        values.update(range(low, high + 1, int(step or 1)))
    return values


def cron_ticks(line: str) -> list[time]:
    """Моменты суток (UTC), в которые срабатывает строка cron, — по возрастанию."""
    minute, hour, *days = line.split()
    assert days == ["*", "*", "*"], f"разбор не знает расписания по дням: {line}"
    return sorted(time(h, m) for h in cron_values(hour, 23) for m in cron_values(minute, 59))


class TestRegistry:
    def test_the_three_jobs_of_the_schedule_are_registered(self) -> None:
        """Имена совпадают с расписанием в .github/workflows/jobs.yml.

        Расхождение здесь не падает: расписание получает 404, а сводка не приходит — и
        причину искать неделю.
        """
        assert set(all_jobs()) == {"morning-summary", "daily-snapshot", "deadline-check"}

    def test_every_schedule_line_is_mapped_to_a_registered_job(self) -> None:
        """Каждая строка cron в jobs.yml сопоставлена задаче, и такая задача есть.

        GitHub передаёт в `github.event.schedule` строку расписания символ в символ, а
        `case` по ней выбирает задачу. Разошлись — и задача молча не запускается: так
        ежечасная проверка сроков не выполнилась ни разу, пока её не нашёл аудит.
        """
        workflow = schedule()
        crons = set(re.findall(r"-\s*cron:\s*'([^']+)'", workflow))
        mapped = case_lines(workflow)

        assert crons, "в jobs.yml не нашлось ни одной строки cron — разбор сломан"
        assert crons == set(mapped), f"cron без задачи или лишний case: {crons ^ set(mapped)}"
        assert set(mapped.values()) <= set(all_jobs())

    def test_the_last_morning_call_is_the_one_the_screen_promises(self) -> None:
        """Экран обещает «расписание повторяет попытку до 11:50» по `LAST_SUMMARY_RUN`, а
        повторяет расписание по строке cron. Разошлись — экран обещает попытки, которых нет.

        И окно порога кончается раньше последнего вызова: время в самом конце окна получило
        бы одну попытку, и один пропуск GitHub оставлял бы руководителя без сводки.
        """
        [line] = [cron for cron, job in case_lines(schedule()).items() if job == "morning-summary"]
        day = date(2026, 9, 20)
        ticks = [
            datetime.combine(day, tick, UTC).astimezone(TASHKENT).time()
            for tick in cron_ticks(line)
        ]
        start, end = SUMMARY_WINDOW

        assert max(ticks) == LAST_SUMMARY_RUN
        assert min(ticks) <= start
        attempts = [tick for tick in ticks if tick >= end]
        assert len(attempts) >= 6, f"у сводки в {end:%H:%M} попыток {len(attempts)}"

    def test_every_job_has_a_period_and_a_title(self) -> None:
        for job in all_jobs().values():
            assert job.title
            assert job.period is not None


class TestIdempotency:
    async def test_the_first_run_does_the_work(
        self, session: AsyncSession, sender: FakePushSender
    ) -> None:
        outcome = await run_job(
            session, "deadline-check", push=sender, now=datetime(2026, 9, 20, 6, tzinfo=UTC)
        )

        assert outcome.status == "done"
        assert outcome.skipped is False
        # Состав ступеней — лестница внимания (ТЗ §4), считанная `services/metrics.py`.
        assert {"needs_attention", "overdue", "burning", "silent"} <= set(outcome.result)

    async def test_the_second_run_in_the_same_period_does_nothing(
        self, session: AsyncSession, sender: FakePushSender
    ) -> None:
        """Так выглядит второй вызов расписания. Не ошибка — просто работа уже сделана."""
        await subscribe(session, PHONE)
        moment = datetime(2026, 9, 20, 6, tzinfo=UTC)
        await run_job(session, "morning-summary", push=sender, now=moment)

        again = await run_job(
            session, "morning-summary", push=sender, now=moment + timedelta(minutes=7)
        )

        assert again.skipped is True
        runs = list(await session.scalars(select(JobRun).where(JobRun.name == "morning-summary")))
        assert len(runs) == 1, "второй вызов завёл второй прогон — сводка ушла бы дважды"

    async def test_the_next_period_runs_again(
        self, session: AsyncSession, sender: FakePushSender
    ) -> None:
        await subscribe(session, PHONE)
        await run_job(
            session, "morning-summary", push=sender, now=datetime(2026, 9, 20, 6, tzinfo=UTC)
        )

        tomorrow = await run_job(
            session, "morning-summary", push=sender, now=datetime(2026, 9, 21, 6, tzinfo=UTC)
        )

        assert (tomorrow.status, tomorrow.skipped) == ("done", False)
        assert len(sender.sent) == 2

    async def test_the_period_of_a_daily_job_is_local(
        self, session: AsyncSession, sender: FakePushSender
    ) -> None:
        """Сутки считаются по Ташкенту: иначе граница дня проходит в пять утра по местному.

        22:00 UTC 20 сентября — это уже 03:00 21 сентября в Ташкенте, и сводка за это
        время относится к 21-му.
        """
        outcome = await run_job(
            session, "daily-snapshot", push=sender, now=datetime(2026, 9, 20, 22, tzinfo=UTC)
        )

        assert outcome.period == "2026-09-21"


class TestFailures:
    async def test_an_unknown_job_is_not_found(
        self, session: AsyncSession, sender: FakePushSender
    ) -> None:
        from app.domain.errors import NotFoundError

        with pytest.raises(NotFoundError) as error:
            await run_job(session, "нет-такой-задачи", push=sender)

        assert "morning-summary" in str(error.value), "отказ обязан назвать, какие есть"

    async def test_a_failed_run_does_not_occupy_the_period(
        self, session: AsyncSession, sender: FakePushSender
    ) -> None:
        """Одна ошибка не должна отменить задачу до конца суток.

        Прогон со статусом `failed` не считается сделанной работой: следующий вызов
        расписания пробует снова.
        """

        async def breaks(_: JobContext) -> dict[str, Any]:
            raise RuntimeError("проверочная поломка")

        name = "test-failing-job"
        if name not in all_jobs():
            register(Job(name=name, title="Проверочная", period=daily_period, handler=breaks))

        moment = datetime(2026, 9, 20, 6, tzinfo=UTC)
        with pytest.raises(RuntimeError):
            await run_job(session, name, push=sender, now=moment)

        # Прогон откатился вместе с работой, поэтому период свободен: вторая попытка
        # доходит до обработчика, а не отвечает «уже сделано».
        with pytest.raises(RuntimeError):
            await run_job(session, name, push=sender, now=moment + timedelta(minutes=5))

    async def test_a_released_failure_keeps_the_work_and_frees_the_period(
        self, session: AsyncSession, sender: FakePushSender
    ) -> None:
        """Внешняя служба не приняла работу: записанное остаётся, период свободен, и след
        неудачи — строка `failed` в той же транзакции, а не откат."""

        async def refused(context: JobContext) -> Release:
            leader = await leader_of(context.session)
            context.session.add(
                Notification(
                    user_id=leader.id,
                    kind="morning_summary",
                    dedup_key=f"test-release:{context.now.isoformat()}",
                    payload={},
                )
            )
            await context.session.flush()
            return Release(status="failed", result={"tried": True}, error="служба не приняла")

        name = "test-refused-job"
        if name not in all_jobs():
            register(Job(name=name, title="Проверочная", period=daily_period, handler=refused))

        moment = datetime(2026, 9, 20, 6, tzinfo=UTC)
        first = await run_job(session, name, push=sender, now=moment)
        second = await run_job(session, name, push=sender, now=moment + timedelta(minutes=5))

        assert (first.status, first.result, first.skipped) == ("failed", {"tried": True}, False)
        assert (second.status, second.skipped) == ("failed", False)
        runs = list(await session.scalars(select(JobRun).where(JobRun.name == name)))
        assert [(run.status, run.error) for run in runs] == [("failed", "служба не приняла")] * 2
        traces = await session.scalars(
            select(Notification.dedup_key).where(Notification.dedup_key.startswith("test-release"))
        )
        assert len(list(traces)) == 2, "работа обработчика откатилась вместе с неудачей"

    async def test_a_forced_run_that_lets_go_keeps_the_done_result(
        self, session: AsyncSession, sender: FakePushSender
    ) -> None:
        """Повторный прогон, отпустивший период, возвращает строке прежний результат."""
        answers: list[dict[str, Any] | Release] = [
            {"number": 1},
            Release(status="not_due", result={"reason": "nothing"}),
        ]

        async def once(_: JobContext) -> dict[str, Any] | Release:
            return answers.pop(0)

        name = "test-once-job"
        if name not in all_jobs():
            register(Job(name=name, title="Проверочная", period=daily_period, handler=once))

        moment = datetime(2026, 9, 20, 6, tzinfo=UTC)
        await run_job(session, name, push=sender, now=moment)
        forced = await run_job(session, name, push=sender, now=moment, force=True)

        assert (forced.status, forced.result) == ("not_due", {"reason": "nothing"})
        [run] = await session.scalars(select(JobRun).where(JobRun.name == name))
        assert (run.status, run.result) == ("done", {"number": 1})


class TestTheEndpoint:
    async def test_the_schedule_runs_a_job_with_its_secret(
        self, api: AsyncClient, settings: Settings
    ) -> None:
        response = await api.post(
            "/internal/jobs/deadline-check",
            headers={SECRET_HEADER: settings.jobs_secret.get_secret_value()},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["job"] == "deadline-check"
        assert body["status"] == "done"

    async def test_without_the_secret_the_endpoint_says_nothing(self, api: AsyncClient) -> None:
        """401, а не 403: тот, кто пришёл без секрета, не «не имеет права», а не назвался."""
        response = await api.post("/internal/jobs/deadline-check")

        assert response.status_code == 401

    async def test_a_wrong_secret_is_refused(self, api: AsyncClient) -> None:
        response = await api.post(
            "/internal/jobs/deadline-check", headers={SECRET_HEADER: "wrong-secret-value-000"}
        )

        assert response.status_code == 401

    async def test_a_session_does_not_open_this_door(self, assistant_api: AsyncClient) -> None:
        """Личная ссылка не даёт права запускать задачи: это вход расписания, не человека."""
        response = await assistant_api.post("/internal/jobs/deadline-check")

        assert response.status_code == 401

    async def test_the_endpoint_is_outside_api(self, api: AsyncClient, settings: Settings) -> None:
        """Путь не начинается с `/api`, и через прокси интерфейса он недоступен (ADR-0028)."""
        through_proxy = await api.post(
            "/api/internal/jobs/deadline-check",
            headers={SECRET_HEADER: settings.jobs_secret.get_secret_value()},
        )

        assert through_proxy.status_code == 404


# 20.09.2026 по Ташкенту (UTC+5): 03:00 UTC — 08:00, до сводки в 08:30; 03:30 — ровно 08:30;
# 06:00 UTC — 11:00.
EARLY = datetime(2026, 9, 20, 3, tzinfo=UTC)
AT_SEND = datetime(2026, 9, 20, 3, 30, tzinfo=UTC)
MORNING = datetime(2026, 9, 20, 6, tzinfo=UTC)
PHONE = "https://web.push.apple.com/leader-phone"
LAPTOP = "https://fcm.googleapis.com/fcm/send/leader-laptop"


async def leader_of(session: AsyncSession) -> User:
    leader = await session.scalar(select(User).where(User.role == Role.LEADER.value))
    assert leader is not None
    return leader


async def subscribe(session: AsyncSession, *endpoints: str) -> None:
    """Подписки руководителя — зафиксированные: неудачный прогон откатывает только своё."""
    leader = await leader_of(session)
    for endpoint in endpoints:
        session.add(
            PushSubscription(
                user_id=leader.id, endpoint=endpoint, p256dh=P256DH, auth=AUTH, device="iPhone"
            )
        )
    await session.commit()


async def summary_of_the_day(
    session: AsyncSession, day: date = date(2026, 9, 20)
) -> Notification | None:
    leader = await leader_of(session)
    found: Notification | None = await session.scalar(
        select(Notification).where(Notification.dedup_key == summary_key(day, leader.id))
    )
    return found


async def summary_runs(session: AsyncSession) -> list[JobRun]:
    return list(await session.scalars(select(JobRun).where(JobRun.name == "morning-summary")))


async def endpoints(session: AsyncSession, *, gone: bool) -> list[str]:
    """Адреса подписок: действующие или отключённые службой (`gone_at`)."""
    marked = PushSubscription.gone_at.is_not(None) if gone else PushSubscription.gone_at.is_(None)
    rows = await session.scalars(
        select(PushSubscription.endpoint).where(marked).order_by(PushSubscription.endpoint)
    )
    return list(rows)


async def summary_at(session: AsyncSession, value: str) -> None:
    """Время сводки в обход проверки порога. «00:00» делает «пора» независимым от часов, на
    которых идёт тест эндпоинта: там время настоящее, а не заданное тестом."""
    setting = await session.scalar(select(Setting).where(Setting.key == "summary_at"))
    assert setting is not None
    setting.value = value
    await session.flush()


class TestMorningSummary:
    """Сводку зовут каждые десять минут, а уходит она одна — в назначенное время (V24).

    День занимает только доставка: «некому» и «нечем» — ожидание, а не закрытый день.
    """

    async def test_before_its_time_it_is_not_due_and_leaves_no_trace(
        self, session: AsyncSession, sender: FakePushSender
    ) -> None:
        """«Ещё не время» не занимает день: иначе сводка не ушла бы уже никогда."""
        await subscribe(session, PHONE)

        outcome = await run_job(session, "morning-summary", push=sender, now=EARLY)

        assert (outcome.status, outcome.skipped) == ("not_due", False)
        assert outcome.result == {"reason": "not_yet"}
        assert await summary_runs(session) == []
        assert sender.sent == []

    async def test_the_time_is_the_threshold_the_assistant_set(
        self, session: AsyncSession, sender: FakePushSender
    ) -> None:
        await subscribe(session, PHONE)
        await summary_at(session, "07:30")

        outcome = await run_job(session, "morning-summary", push=sender, now=EARLY)

        assert outcome.status == "done"

    async def test_it_goes_to_the_leader_and_is_marked_sent(
        self, session: AsyncSession, sender: FakePushSender
    ) -> None:
        await subscribe(session, PHONE)

        outcome = await run_job(session, "morning-summary", push=sender, now=MORNING)

        assert outcome.status == "done"
        assert outcome.result["delivered"] is True
        assert (outcome.result["devices"], outcome.result["reason"]) == (1, "sent")
        assert {"awaiting_decision", "burning", "on_track"} <= set(outcome.result)
        [push] = sender.sent
        assert push.target.endpoint == PHONE
        assert (push.ttl, push.urgency) == (43200, "normal")
        assert push.payload == {
            "kind": "summary",
            "tag": "morning-summary:2026-09-20",
            "url": "/?view=summary",
            "lock_screen": {"awaiting": None, "due": None},
        }
        notification = await summary_of_the_day(session)
        assert notification is not None
        assert notification.sent_at == MORNING

    async def test_the_second_call_of_the_day_sends_nothing(
        self, session: AsyncSession, sender: FakePushSender
    ) -> None:
        """Инвариант 10: расписание зовёт до 11:50, пуш уходит один."""
        await subscribe(session, PHONE)

        await run_job(session, "morning-summary", push=sender, now=MORNING)
        again = await run_job(
            session, "morning-summary", push=sender, now=MORNING + timedelta(minutes=10)
        )

        assert again.skipped is True
        assert len(sender.sent) == 1

    async def test_a_forced_run_does_not_send_the_day_twice(
        self, session: AsyncSession, sender: FakePushSender
    ) -> None:
        await subscribe(session, PHONE)
        await run_job(session, "morning-summary", push=sender, now=MORNING)

        forced = await run_job(session, "morning-summary", push=sender, now=MORNING, force=True)

        assert forced.result["reason"] == "sent"
        assert len(sender.sent) == 1

    async def test_without_a_device_the_day_waits_for_the_leader(
        self, session: AsyncSession, sender: FakePushSender
    ) -> None:
        """Руководитель включил уведомления в 09:00 — сводка приходит в 09:10, а не завтра."""
        first = await run_job(session, "morning-summary", push=sender, now=AT_SEND)

        assert (first.status, first.result) == ("not_due", {"reason": "no_device"})
        assert await summary_runs(session) == []

        await subscribe(session, PHONE)
        later = AT_SEND + timedelta(minutes=40)
        second = await run_job(session, "morning-summary", push=sender, now=later)

        assert (second.status, second.result["reason"]) == ("done", "sent")
        [push] = sender.sent
        assert push.target.endpoint == PHONE
        notification = await summary_of_the_day(session)
        assert notification is not None
        assert notification.sent_at == later

    async def test_without_a_key_the_day_waits_for_it(self, session: AsyncSession) -> None:
        """Заказчик ввёл ключ посреди утра — сводка уходит первым же вызовом после этого."""
        await subscribe(session, PHONE)
        unconfigured = FakePushSender(public_key=None)

        first = await run_job(session, "morning-summary", push=unconfigured, now=AT_SEND)

        assert (first.status, first.result) == ("not_due", {"reason": "not_configured"})
        assert unconfigured.sent == []
        assert await summary_runs(session) == []

        configured = FakePushSender()
        later = AT_SEND + timedelta(minutes=40)
        second = await run_job(session, "morning-summary", push=configured, now=later)

        assert (second.status, second.result["reason"]) == ("done", "sent")
        assert len(configured.sent) == 1
        notification = await summary_of_the_day(session)
        assert notification is not None
        assert notification.sent_at == later

    async def test_a_subscription_that_is_gone_is_marked_and_skipped(
        self, session: AsyncSession, sender: FakePushSender
    ) -> None:
        """Служба ответила «такой подписки нет» — завтра по ней уже не стучимся."""
        await subscribe(session, PHONE, LAPTOP)
        sender.outcomes[PHONE] = PushOutcome.GONE

        outcome = await run_job(session, "morning-summary", push=sender, now=MORNING)

        assert (outcome.result["devices"], outcome.result["reason"]) == (1, "sent")
        assert await endpoints(session, gone=False) == [LAPTOP]
        assert await endpoints(session, gone=True) == [PHONE]

    async def test_when_every_device_is_gone_the_day_stays_open(
        self, session: AsyncSession, sender: FakePushSender
    ) -> None:
        """Отключённые службой устройства — «некому», а не закрытый день: включит
        руководитель уведомления заново — сводка уйдёт следующим вызовом."""
        await subscribe(session, PHONE)
        sender.outcomes[PHONE] = PushOutcome.GONE

        outcome = await run_job(session, "morning-summary", push=sender, now=MORNING)

        assert (outcome.status, outcome.result["reason"]) == ("not_due", "no_device")
        assert await summary_runs(session) == []
        assert await endpoints(session, gone=True) == [PHONE]
        notification = await summary_of_the_day(session)
        assert notification is not None
        assert notification.sent_at is None

        again = await run_job(
            session, "morning-summary", push=sender, now=MORNING + timedelta(minutes=10)
        )

        assert (again.status, again.result) == ("not_due", {"reason": "no_device"})
        assert len(sender.sent) == 1, "отключённому адресу постучались снова"

        await subscribe(session, LAPTOP)
        later = MORNING + timedelta(minutes=20)
        enabled_again = await run_job(session, "morning-summary", push=sender, now=later)

        assert (enabled_again.status, enabled_again.result["reason"]) == ("done", "sent")
        assert [push.target.endpoint for push in sender.sent] == [PHONE, LAPTOP]
        await session.refresh(notification)
        assert notification.sent_at == later

    async def test_when_no_service_accepts_it_the_run_fails_and_the_day_stays_free(
        self, session: AsyncSession, sender: FakePushSender
    ) -> None:
        """Служба не приняла сводку ни для одного устройства — прогон неудачный, и через
        десять минут расписание пробует снова, а не закрывает день без сводки."""
        await subscribe(session, PHONE)
        sender.outcomes[PHONE] = PushOutcome.FAILED

        outcome = await run_job(session, "morning-summary", push=sender, now=MORNING)

        assert (outcome.status, outcome.result["reason"]) == ("failed", "refused")
        [run] = await summary_runs(session)
        assert run.status == "failed"
        assert run.error is not None
        assert "не доставлена" in run.error
        notification = await summary_of_the_day(session)
        assert notification is not None, "уведомление откатилось вместе с неудачей"
        assert notification.sent_at is None

        sender.outcomes.clear()
        later = MORNING + timedelta(minutes=10)
        retry = await run_job(session, "morning-summary", push=sender, now=later)

        assert (retry.status, retry.result["reason"]) == ("done", "sent")
        await session.refresh(notification)
        assert notification.sent_at == later

    async def test_a_gone_device_stays_marked_when_another_one_fails(
        self, session: AsyncSession, sender: FakePushSender
    ) -> None:
        """Неудача на одном устройстве не возвращает к жизни отключённое другое: иначе
        каждое утро сводка снова стучалась бы в пустоту."""
        await subscribe(session, PHONE, LAPTOP)
        sender.outcomes.update({PHONE: PushOutcome.GONE, LAPTOP: PushOutcome.FAILED})

        outcome = await run_job(session, "morning-summary", push=sender, now=MORNING)

        assert outcome.status == "failed"
        assert await endpoints(session, gone=False) == [LAPTOP]
        assert await endpoints(session, gone=True) == [PHONE]

    async def test_an_address_that_cannot_be_sent_to_does_not_stop_the_others(
        self, session: AsyncSession
    ) -> None:
        """Строка с адресом, который httpx не разберёт (записана до проверки адреса или в
        обход неё), — неудача одного устройства, а не оборванная рассылка: телефон после
        неё сводку получает. Отправитель настоящий — подделка не знает, что бросает httpx."""
        leader = await leader_of(session)
        phone_key = ec.generate_private_key(ec.SECP256R1()).public_key()
        p256dh = (
            base64.urlsafe_b64encode(
                phone_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
            )
            .rstrip(b"=")
            .decode("ascii")
        )
        # Мягкий перенос в имени хоста: подпись и шифрование проходят, а httpx отказывается
        # уже на самой отправке (`httpx.InvalidURL`, не наследник `httpx.HTTPError`).
        broken = "https://old­.fcm.googleapis.com/fcm/send/old-laptop"
        for endpoint, age in ((broken, 2), (PHONE, 1)):
            session.add(
                PushSubscription(
                    user_id=leader.id,
                    endpoint=endpoint,
                    p256dh=p256dh,
                    auth=AUTH,
                    device="iPhone",
                    created_at=MORNING - timedelta(days=age),
                )
            )
        await session.commit()
        posted: list[str] = []

        def service(request: httpx.Request) -> httpx.Response:
            posted.append(str(request.url))
            return httpx.Response(201)

        sender = WebPushSender(
            new_private_key(), MAILTO_SUBJECT, transport=httpx.MockTransport(service)
        )

        outcome = await run_job(session, "morning-summary", push=sender, now=MORNING)

        assert (outcome.status, outcome.result["reason"]) == ("done", "sent")
        assert outcome.result["devices"] == 1
        assert posted == [PHONE]

    async def test_force_does_not_wait_for_the_time(
        self, session: AsyncSession, sender: FakePushSender
    ) -> None:
        """`--force` — для разработки и разбора: сводку можно отправить до её времени."""
        await subscribe(session, PHONE)

        outcome = await run_job(session, "morning-summary", push=sender, now=EARLY, force=True)

        assert (outcome.status, outcome.result["reason"]) == ("done", "sent")

    async def test_the_endpoint_sends_through_the_port_of_the_application(
        self, api: AsyncClient, push: FakePushSender, settings: Settings, session: AsyncSession
    ) -> None:
        """Эндпоинт расписания берёт отправитель у приложения — тот же порт, что у вопроса.

        Подделка без ключа: по причине «не настроено» видно, чей отправитель дошёл до
        сводки.
        """
        await summary_at(session, "00:00")
        push.public_key = None

        response = await api.post(
            "/internal/jobs/morning-summary",
            headers={SECRET_HEADER: settings.jobs_secret.get_secret_value()},
        )

        assert response.status_code == 200
        body = response.json()
        assert (body["status"], body["result"]) == ("not_due", {"reason": "not_configured"})

    async def test_the_endpoint_answers_503_and_keeps_what_the_run_wrote(
        self, api: AsyncClient, push: FakePushSender, settings: Settings, session: AsyncSession
    ) -> None:
        """503 — чтобы расписание повторило попытку и покраснело; но записанное прогоном
        (уведомление, строка неудачи) фиксируется, а не откатывается исключением."""
        await summary_at(session, "00:00")
        await subscribe(session, PHONE)
        push.outcomes[PHONE] = PushOutcome.FAILED

        response = await api.post(
            "/internal/jobs/morning-summary",
            headers={SECRET_HEADER: settings.jobs_secret.get_secret_value()},
        )

        assert response.status_code == 503
        body = response.json()
        assert (body["status"], body["result"]["reason"]) == ("failed", "refused")
        [run] = await summary_runs(session)
        assert run.status == "failed"
        notification = await summary_of_the_day(
            session, local_date(now_utc(), ZoneInfo(settings.timezone))
        )
        assert notification is not None
        assert notification.sent_at is None
