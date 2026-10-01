"""Правила раздела «Программы»: «успеваем?», горизонт, окно темпа, отсчёт (V13, V14)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain.programs import (
    HORIZON_YEARS,
    PACE_WINDOW_DAYS,
    PaceVerdict,
    days_left,
    horizon,
    in_window,
    pace,
    window_start,
    year_end,
)

TODAY = date(2026, 9, 27)


class TestPace:
    def test_little_data_below_the_threshold(self) -> None:
        answer = pace(
            today=TODAY,
            due_on=TODAY + timedelta(days=30),
            closed=12,
            closed_tasks=9,
            remaining=40,
            min_closed_tasks=10,
        )
        assert answer.verdict is PaceVerdict.LITTLE_DATA
        assert (answer.forecast_on, answer.gap_days) == (None, None)
        # Числа под «мало данных» всё равно отдаются: фраза называет, сколько закрыто.
        assert (answer.closed, answer.closed_tasks, answer.remaining) == (12, 9, 40)

    def test_forecast_rounds_up_to_whole_days(self) -> None:
        # 83 оставшихся при 11 закрытых за 90 дней: 83 × 90 / 11 = 679,1 → 680 дней.
        answer = pace(
            today=TODAY,
            due_on=TODAY + timedelta(days=591),
            closed=11,
            closed_tasks=10,
            remaining=83,
            min_closed_tasks=10,
        )
        assert answer.forecast_on == TODAY + timedelta(days=680)
        assert answer.gap_days == 89
        assert answer.verdict is PaceVerdict.BEHIND

    def test_forecast_on_the_date_is_in_time(self) -> None:
        answer = pace(
            today=TODAY,
            due_on=TODAY + timedelta(days=90),
            closed=10,
            closed_tasks=10,
            remaining=10,
            min_closed_tasks=10,
        )
        assert (answer.gap_days, answer.verdict) == (0, PaceVerdict.ON_TRACK)

    def test_nothing_left_is_in_time(self) -> None:
        answer = pace(
            today=TODAY,
            due_on=TODAY,
            closed=10,
            closed_tasks=10,
            remaining=0,
            min_closed_tasks=10,
        )
        assert (answer.forecast_on, answer.verdict) == (TODAY, PaceVerdict.ON_TRACK)

    def test_nothing_left_after_the_date_is_not_behind(self) -> None:
        # Всё закрыто, а дата прошла: «не хватает 7 дн» при «осталось 0» было бы неправдой.
        answer = pace(
            today=TODAY,
            due_on=TODAY - timedelta(days=7),
            closed=12,
            closed_tasks=12,
            remaining=0,
            min_closed_tasks=10,
        )
        assert (answer.verdict, answer.forecast_on, answer.gap_days) == (
            PaceVerdict.ON_TRACK,
            TODAY,
            0,
        )

    def test_zero_closed_never_divides(self) -> None:
        answer = pace(
            today=TODAY, due_on=TODAY, closed=0, closed_tasks=0, remaining=5, min_closed_tasks=0
        )
        assert answer.verdict is PaceVerdict.LITTLE_DATA


class TestWindow:
    def test_the_boundary_day_is_outside_today_inside(self) -> None:
        start = window_start(TODAY)
        assert start == TODAY - timedelta(days=PACE_WINDOW_DAYS)
        assert not in_window(start, today=TODAY)
        assert in_window(start + timedelta(days=1), today=TODAY)
        assert in_window(TODAY, today=TODAY)

    @pytest.mark.parametrize("day", [None, TODAY + timedelta(days=1)])
    def test_nothing_or_future_is_outside(self, day: date | None) -> None:
        assert not in_window(day, today=TODAY)


class TestHorizonAndCountdown:
    def test_five_years_from_the_current(self) -> None:
        assert horizon(TODAY) == (2026, 2026 + HORIZON_YEARS - 1) == (2026, 2030)
        assert horizon(date(2027, 1, 1)) == (2027, 2031)

    def test_year_end(self) -> None:
        assert year_end(TODAY) == date(2026, 12, 31)

    def test_days_left_by_calendar_days(self) -> None:
        assert days_left(due_on=date(2028, 5, 10), today=TODAY) == 591
        assert days_left(due_on=TODAY, today=TODAY) == 0
        assert days_left(due_on=date(2026, 8, 31), today=TODAY) == -27
