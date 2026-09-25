"""Лестница внимания: правило ступеней и порядок строк (ТЗ 4).

Чистые проверки без базы: правило живёт в домене, и его граничные случаи дешевле всего
перебрать здесь. Сборка снимка из базы и совпадение чисел во всех местах проверяются в
`test_metrics.py`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.attention import (
    LADDER,
    Attention,
    Item,
    Ladder,
    build_ladder,
    with_due_changes,
)
from app.domain.clock import local_date

TODAY = date(2026, 9, 26)
TASHKENT = ZoneInfo("Asia/Tashkent")
BURN = 7
QUIET = 14


def item(
    *,
    due_on: date | None = None,
    life: date | None = TODAY,
    awaiting_since: date | None = None,
    outside: bool = False,
    section: str = "projects",
    title: str = "работа",
) -> Item:
    return Item(
        section=section,
        entity_id=uuid.uuid4(),
        title=title,
        due_on=due_on,
        last_sign_of_life=life,
        awaiting_since=awaiting_since,
        lead_is_outside=outside,
        responsible_person_id=None,
    )


def ladder_of(*items: Item) -> Ladder:
    return build_ladder(items, today=TODAY, burn_days=BURN, quiet_days=QUIET)


def days(n: int) -> date:
    return date.fromordinal(TODAY.toordinal() + n)


class TestSteps:
    def test_every_step_in_ladder_order(self) -> None:
        """Одна запись на каждую ступень — строки идут ровно в порядке ТЗ 4."""
        result = ladder_of(
            item(title="молчит", life=days(-30)),
            item(title="горит", due_on=days(3)),
            item(title="по плану", due_on=days(60)),
            item(title="ждёт решения", awaiting_since=days(-2)),
            item(title="чужие", life=days(-30), outside=True),
            item(title="просрочено", due_on=days(-1)),
        )

        assert [row.attention for row in result.rows] == list(LADDER[:-1])
        assert result.on_track == 1

    def test_question_outranks_the_deadline(self) -> None:
        """Пока руководитель не ответил, требовать срок не с кого."""
        result = ladder_of(item(due_on=days(-10), awaiting_since=days(-3)))

        assert result.rows[0].attention is Attention.AWAITING_DECISION
        assert result.rows[0].deviation == 3, "отклонение — дни ожидания решения"

    def test_outside_lead_with_movement_is_on_track(self) -> None:
        """«Зависит от чужих» — только когда с их стороны нет движения (ТЗ 4)."""
        result = ladder_of(item(outside=True, life=days(-2)))

        assert result.rows == ()
        assert result.on_track == 1

    def test_outside_lead_in_silence_waits_for_others_not_for_us(self) -> None:
        result = ladder_of(item(outside=True, life=days(-20)))

        assert result.rows[0].attention is Attention.BLOCKED_BY_OTHERS
        assert result.rows[0].deviation == 20, "отклонение — дни тишины"

    def test_silence_is_counted_after_the_threshold(self) -> None:
        exactly = ladder_of(item(life=days(-QUIET)))
        beyond = ladder_of(item(life=days(-QUIET - 1)))

        assert exactly.on_track == 1, "ровно порог — ещё не молчание"
        assert beyond.rows[0].attention is Attention.SILENT

    def test_record_without_own_movement_is_never_silent(self) -> None:
        """Молчание вехи — это молчание проекта: второй строкой его не показываем."""
        result = ladder_of(item(section="milestones", life=None))

        assert result.on_track == 1

    def test_burn_threshold_is_inclusive(self) -> None:
        assert ladder_of(item(due_on=days(BURN))).rows[0].attention is Attention.BURNING
        assert ladder_of(item(due_on=days(BURN + 1))).on_track == 1

    def test_due_today_burns_and_is_not_overdue(self) -> None:
        result = ladder_of(item(due_on=TODAY))

        assert result.rows[0].attention is Attention.BURNING
        assert result.rows[0].deviation == 0


class TestOrderWithinStep:
    def test_nearest_burning_deadline_comes_first(self) -> None:
        """«Горит сегодня» выше «горит через шесть дней» — по срочности, а не наоборот."""
        result = ladder_of(
            item(title="через 6", due_on=days(6)),
            item(title="сегодня", due_on=TODAY),
            item(title="через 2", due_on=days(2)),
        )

        assert [row.title for row in result.rows] == ["сегодня", "через 2", "через 6"]

    def test_most_overdue_comes_first(self) -> None:
        result = ladder_of(
            item(title="1 день", due_on=days(-1)),
            item(title="20 дней", due_on=days(-20)),
        )

        assert [row.title for row in result.rows] == ["20 дней", "1 день"]

    def test_oldest_question_comes_first(self) -> None:
        result = ladder_of(
            item(title="вчера", awaiting_since=days(-1)),
            item(title="неделю", awaiting_since=days(-7)),
        )

        assert [row.title for row in result.rows] == ["неделю", "вчера"]

    def test_longest_silence_comes_first(self) -> None:
        result = ladder_of(
            item(title="15", life=days(-15)),
            item(title="40", life=days(-40)),
        )

        assert [row.title for row in result.rows] == ["40", "15"]


class TestWhatIf:
    def test_changed_deadline_moves_the_record_and_leaves_the_original(self) -> None:
        """«Что если» считает тем же кодом по копии снимка (инвариант 2)."""
        work = item(due_on=days(30))
        snapshot = (work,)

        changed = with_due_changes(snapshot, {(work.section, work.entity_id): days(2)})

        assert ladder_of(*snapshot).on_track == 1
        assert ladder_of(*changed).rows[0].attention is Attention.BURNING
        assert snapshot[0].due_on == days(30), "исходный снимок не тронут"

    def test_change_of_an_unknown_record_is_an_error_not_a_silent_skip(self) -> None:
        with pytest.raises(KeyError):
            with_due_changes((item(),), {("projects", uuid.uuid4()): TODAY})


class TestTashkentDay:
    def test_utc_evening_is_the_next_day_in_tashkent(self) -> None:
        """Срок 26.09 03:00 по Ташкенту хранится как 25.09 22:00 UTC (инвариант 8)."""
        stored = datetime(2026, 9, 25, 22, 0, tzinfo=UTC)

        assert local_date(stored, TASHKENT) == date(2026, 9, 26)

    def test_moment_without_zone_is_refused(self) -> None:
        with pytest.raises(ValueError, match="часового пояса"):
            local_date(datetime(2026, 9, 25, 22, 0), TASHKENT)  # noqa: DTZ001
