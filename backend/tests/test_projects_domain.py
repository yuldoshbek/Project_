"""Правила проекта без базы: вехи шаблона, горизонт дат, свежесть «что мешает», текст."""

from __future__ import annotations

from datetime import date

import pytest

from app.domain.dictionaries import ProjectStatus
from app.domain.errors import RuleViolationError
from app.domain.projects import (
    has_active_impediment,
    impediment_is_stale,
    project_lag,
    project_readiness,
    template_dates,
    validate_horizon,
    validate_program,
    validate_title,
)

START = date(2026, 9, 1)


class TestTemplateDates:
    def test_as_written_without_due(self) -> None:
        assert template_dates(started_on=START, due_on=None, offsets=[30, 60, 90]) == [
            date(2026, 10, 1),
            date(2026, 10, 31),
            date(2026, 11, 30),
        ]

    def test_later_due_does_not_stretch(self) -> None:
        later = template_dates(started_on=START, due_on=date(2027, 6, 1), offsets=[30, 90])
        assert later == [date(2026, 10, 1), date(2026, 11, 30)]

    def test_earlier_due_compresses_in_order(self) -> None:
        """Ни одна веха не позже срока проекта, порядок сохранён."""
        due = date(2026, 11, 30)  # 90 дней, а шаблон — 150
        dates = template_dates(started_on=START, due_on=due, offsets=[30, 120, 150])
        assert dates == sorted(dates)
        assert dates[-1] == due
        assert all(day <= due for day in dates)

    def test_empty_template(self) -> None:
        assert template_dates(started_on=START, due_on=None, offsets=[]) == []


class TestHorizon:
    @pytest.mark.parametrize("day", [date(1999, 12, 31), date(2101, 1, 1), date(9999, 12, 1)])
    def test_outside(self, day: date) -> None:
        with pytest.raises(RuleViolationError):
            validate_horizon(START, day)

    def test_inside(self) -> None:
        validate_horizon(date(2000, 1, 1), date(2100, 12, 31))


class TestImpediment:
    def test_stale_by_calendar_days(self) -> None:
        """Порог 14: пятнадцатый день — устарела, четырнадцатый — ещё нет. Час не важен."""
        today = date(2026, 9, 25)
        assert not impediment_is_stale(updated_on=date(2026, 9, 11), today=today, stale_days=14)
        assert impediment_is_stale(updated_on=date(2026, 9, 10), today=today, stale_days=14)
        assert not impediment_is_stale(updated_on=None, today=today, stale_days=14)

    def test_active(self) -> None:
        today = date(2026, 9, 25)
        assert has_active_impediment(
            impediment="Ждём письмо", updated_on=today, today=today, stale_days=14
        )
        assert not has_active_impediment(
            impediment="  ", updated_on=today, today=today, stale_days=14
        )


class TestRules:
    def test_nul_in_title(self) -> None:
        with pytest.raises(RuleViolationError):
            validate_title("Проект" + chr(0))

    def test_program_rules(self) -> None:
        validate_program(is_multiyear=True, parent_is_multiyear=None)
        validate_program(is_multiyear=False, parent_is_multiyear=True)
        with pytest.raises(RuleViolationError):
            validate_program(is_multiyear=False, parent_is_multiyear=False)
        with pytest.raises(RuleViolationError):
            validate_program(is_multiyear=True, parent_is_multiyear=True)

    def test_done_is_ready_and_closed_does_not_lag(self) -> None:
        assert (
            project_readiness(
                status=ProjectStatus.DONE,
                passed_milestones=0,
                total_milestones=3,
                done_tasks=0,
                total_tasks=0,
            )
            == 100
        )
        assert (
            project_lag(
                status=ProjectStatus.CANCELLED,
                started_on=START,
                due_on=date(2026, 10, 1),
                today=date(2026, 12, 1),
                readiness_pct=0,
            )
            == 0
        )
