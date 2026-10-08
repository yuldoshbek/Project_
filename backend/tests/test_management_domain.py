"""Правила Управления без базы: действия обхода, неделя, пороги, справочники (V20–V22)."""

from __future__ import annotations

from datetime import date

import pytest

from app.domain.dictionaries import SettingKey, TaskStatus
from app.domain.errors import RuleViolationError
from app.domain.management import (
    NEEDS_INPUT,
    RECORD_OF,
    THRESHOLD_DEFAULTS,
    DictionaryKind,
    RecordKind,
    RoundAction,
    RoundReason,
    ThresholdOrigin,
    actions_for,
    clean_input,
    clean_name,
    clean_offset,
    clean_threshold,
    moved_due,
    renamed_script,
    week_start,
)

TUESDAY = date(2026, 9, 29)


class TestRound:
    def test_every_reason_has_two_or_three_actions_and_no_all_right(self) -> None:
        for reason in RoundReason:
            actions = actions_for(reason, task_status=TaskStatus.IN_PROGRESS)
            assert 2 <= len(actions) <= 3, reason
            assert "ok" not in {action.value for action in actions}

    def test_new_task_has_no_done(self) -> None:
        assert RoundAction.TASK_DONE not in actions_for(
            RoundReason.TASK_OVERDUE, task_status=TaskStatus.NEW
        )
        assert actions_for(RoundReason.TASK_OVERDUE, task_status=TaskStatus.IN_PROGRESS)[0] is (
            RoundAction.TASK_DONE
        )

    def test_every_reason_names_the_record_it_changes(self) -> None:
        assert set(RECORD_OF) == set(RoundReason)
        assert RECORD_OF[RoundReason.MILESTONE_PASSED] is RecordKind.MILESTONE

    def test_order_is_the_priority(self) -> None:
        assert [reason.rank for reason in RoundReason] == list(range(len(RoundReason)))
        assert RoundReason.TASK_OVERDUE.rank < RoundReason.TASK_UNASSIGNED.rank

    def test_week_from_monday_and_move_from_today(self) -> None:
        assert week_start(TUESDAY) == date(2026, 9, 28)
        assert week_start(date(2026, 9, 28)) == date(2026, 9, 28)
        assert moved_due(TUESDAY) == date(2026, 10, 6)

    @pytest.mark.parametrize("action", sorted(NEEDS_INPUT))
    def test_input_is_required_where_it_is_asked(self, action: RoundAction) -> None:
        with pytest.raises(RuleViolationError):
            clean_input(action, "   ")
        assert clean_input(action, "  Ждём ответ  ") == "Ждём ответ"


class TestThresholds:
    def test_defaults_cover_every_key_and_say_where_they_come_from(self) -> None:
        assert set(THRESHOLD_DEFAULTS) == set(SettingKey)
        assert THRESHOLD_DEFAULTS[SettingKey.BURN_DAYS] == (7, ThresholdOrigin.TZ)
        assert THRESHOLD_DEFAULTS[SettingKey.HOT_DAY_THRESHOLD][1] is ThresholdOrigin.ASSUMPTION

    @pytest.mark.parametrize(
        ("value_type", "value", "low", "high"),
        [
            ("days", 0, 1, 60),
            ("days", 61, 1, 60),
            ("days", 7.5, 1, 60),
            ("days", True, 1, 60),
            ("days", "7", 1, 60),
            ("time", "8:30", None, None),
            ("time", "24:00", None, None),
            ("time", "08:30\n", None, None),
            ("time", 830, None, None),
        ],
    )
    def test_refused(
        self, value_type: str, value: object, low: int | None, high: int | None
    ) -> None:
        with pytest.raises(RuleViolationError):
            clean_threshold(value_type=value_type, value=value, low=low, high=high)

    def test_accepted(self) -> None:
        assert clean_threshold(value_type="days", value=60, low=1, high=60) == 60
        assert clean_threshold(value_type="time", value="08:30", low=None, high=None) == "08:30"


class TestDictionaries:
    def test_flags(self) -> None:
        assert not DictionaryKind.TASK_STATUSES.can_disable
        assert not DictionaryKind.REGIONS.can_add
        assert not DictionaryKind.ORGANIZATIONS.can_move
        assert DictionaryKind.DIRECTIONS.can_add and DictionaryKind.DIRECTIONS.can_move

    def test_uzbek_names_follow_only_untranslated(self) -> None:
        assert renamed_script(old_ru="Прочее", current="Прочее", new_ru="Иное") == "Иное"
        assert renamed_script(old_ru="Прочее", current="Бошқа", new_ru="Иное") == "Бошқа"

    def test_name_and_offset(self) -> None:
        assert clean_name("  Стандарт  ") == "Стандарт"
        for bad in ("   ", "Имя" + chr(0), "я" * 201):
            with pytest.raises(RuleViolationError):
                clean_name(bad)
        assert clean_offset(0) == 0
        for bad_offset in (-1, 3651):
            with pytest.raises(RuleViolationError):
                clean_offset(bad_offset)
