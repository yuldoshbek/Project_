"""Календарь: срок проекта в день его вехи и горячие дни (ТЗ 5; V15)."""

import uuid
from datetime import date

from app.domain.calendar import (
    CalendarKind,
    HotDay,
    Mark,
    ProjectEnd,
    ends_with_milestone,
    hot_days,
    window,
)

DAY = date(2026, 10, 18)
PROJECT = uuid.uuid4()
OTHER = uuid.uuid4()


def test_project_end_goes_to_its_milestone_on_the_same_day() -> None:
    first, second, foreign = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    merged = ends_with_milestone(
        [ProjectEnd(project_id=PROJECT, due_on=DAY, is_done=False)],
        [
            Mark(milestone_id=foreign, project_id=OTHER, due_on=DAY, is_done=False),
            Mark(milestone_id=first, project_id=PROJECT, due_on=DAY, is_done=False),
            Mark(milestone_id=second, project_id=PROJECT, due_on=DAY, is_done=False),
        ],
    )
    # Своя веха, а не чужая в тот же день; из двух своих — первая по порядку.
    assert merged == {PROJECT: first}


def test_different_day_or_state_does_not_merge() -> None:
    mark = uuid.uuid4()
    assert not ends_with_milestone(
        [ProjectEnd(project_id=PROJECT, due_on=DAY, is_done=False)],
        [Mark(milestone_id=mark, project_id=PROJECT, due_on=date(2026, 10, 17), is_done=False)],
    )
    # Закрытый проект с открытой вехой — два разных факта.
    assert not ends_with_milestone(
        [ProjectEnd(project_id=PROJECT, due_on=DAY, is_done=True)],
        [Mark(milestone_id=mark, project_id=PROJECT, due_on=DAY, is_done=False)],
    )


def test_hot_day_is_threshold_and_more_open_dates() -> None:
    dates = [
        (DAY, CalendarKind.TASK),
        (DAY, CalendarKind.MILESTONE),
        (DAY, CalendarKind.MILESTONE),
        (date(2026, 10, 19), CalendarKind.TASK),
        (date(2026, 10, 19), CalendarKind.CYCLE),
    ]
    found = hot_days(dates, since=date(2026, 10, 1), until=date(2026, 10, 31), threshold=3)
    assert found == [
        HotDay(date=DAY, count=3, kinds={CalendarKind.MILESTONE: 2, CalendarKind.TASK: 1})
    ]
    # Порядок видов — порядок показа, а не порядок прихода.
    assert list(found[0].kinds) == [CalendarKind.MILESTONE, CalendarKind.TASK]
    assert hot_days(dates, since=date(2026, 10, 1), until=date(2026, 10, 31), threshold=2)[
        1
    ] == HotDay(
        date=date(2026, 10, 19),
        count=2,
        kinds={CalendarKind.TASK: 1, CalendarKind.CYCLE: 1},
    )


def test_days_outside_the_window_are_not_hot() -> None:
    dates = [(DAY, CalendarKind.TASK)] * 3
    assert hot_days(dates, since=date(2026, 10, 19), until=date(2026, 10, 31), threshold=3) == []
    assert hot_days(dates, since=date(2026, 10, 1), until=date(2026, 10, 17), threshold=3) == []


def test_window_starts_today() -> None:
    assert window(date(2026, 9, 28), 28) == (date(2026, 9, 28), date(2026, 10, 25))
