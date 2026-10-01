"""Правила «Взаимодействия» без базы: медиана, скорость, состояние письма, ступени."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.domain.attention import Attention, Item, attention_of, build_ladder
from app.domain.errors import RuleViolationError
from app.domain.interaction import (
    AgreementLine,
    Direction,
    LetterLine,
    LetterState,
    OrganizationSpeed,
    Question,
    answers,
    check_answer,
    check_rating,
    letter_state,
    median_days,
    speed,
)

TODAY = date(2026, 10, 1)


class TestSpeed:
    def test_median_rounds_half_up(self) -> None:
        """9,5 дня — «10 дн», как на утверждённом экране."""
        assert median_days([7, 8, 9, 10, 11, 12]) == 10
        assert median_days([22, 23, 25, 29, 34]) == 25

    def test_one_slow_reply_does_not_spoil_the_median(self) -> None:
        assert median_days([5, 6, 7, 8, 180]) == 7

    def test_no_speed_below_the_threshold(self) -> None:
        assert speed([3, 4, 5, 6], min_letters=5) is None
        assert speed([3, 4, 5, 6, 7], min_letters=5) == 5


class TestLetters:
    def test_state_is_computed(self) -> None:
        assert letter_state(Direction.OUTGOING, None) is LetterState.WAITING_REPLY
        assert letter_state(Direction.INCOMING, None) is LetterState.TO_ANSWER
        assert letter_state(Direction.INCOMING, TODAY) is LetterState.ANSWERED

    def test_answer_dates_are_honest(self) -> None:
        with pytest.raises(RuleViolationError):
            check_answer(sent_on=TODAY, answered_on=date(2026, 9, 30), today=TODAY)
        with pytest.raises(RuleViolationError):
            check_answer(sent_on=date(2026, 9, 1), answered_on=date(2026, 10, 2), today=TODAY)

    def test_only_a_received_reply_is_rated(self) -> None:
        with pytest.raises(RuleViolationError):
            check_rating(Direction.INCOMING, TODAY)
        with pytest.raises(RuleViolationError):
            check_rating(Direction.OUTGOING, None)
        check_rating(Direction.OUTGOING, TODAY)


class TestLadder:
    def test_a_promise_of_others_waits_instead_of_being_overdue(self) -> None:
        """Попрошенный у них срок прошёл — ждём чужих, а не «просрочено» (V39)."""

        def step(due: date) -> Attention:
            return attention_of(
                awaiting_since=None,
                due_on=due,
                today=TODAY,
                last_sign_of_life=due,
                lead_is_outside=True,
                burn_days=7,
                quiet_days=14,
                due_is_others=True,
            )

        assert step(date(2026, 9, 25)) is Attention.BLOCKED_BY_OTHERS
        assert step(date(2026, 10, 3)) is Attention.ON_TRACK

    def test_an_agreement_sleeps_on_its_own_threshold(self) -> None:
        def item(moved: date) -> Item:
            return Item(
                section="agreements",
                entity_id=uuid.uuid4(),
                title="Меморандум",
                due_on=None,
                last_sign_of_life=moved,
                awaiting_since=None,
                lead_is_outside=False,
                responsible_person_id=None,
                quiet_days=90,
            )

        ladder = build_ladder(
            [item(date(2026, 7, 15)), item(date(2026, 6, 1))],
            today=TODAY,
            burn_days=7,
            quiet_days=14,
        )
        assert [(row.attention, row.deviation) for row in ladder.rows] == [(Attention.SILENT, 122)]
        assert ladder.on_track == 1


class TestAnswers:
    def test_four_answers(self) -> None:
        org_a, org_b = uuid.uuid4(), uuid.uuid4()
        letters = [
            LetterLine(uuid.uuid4(), org_a, LetterState.WAITING_REPLY, None, None, 20),
            LetterLine(uuid.uuid4(), org_a, LetterState.WAITING_REPLY, None, None, 5),
            LetterLine(
                uuid.uuid4(), org_b, LetterState.TO_ANSWER, Attention.OVERDUE, date(2026, 9, 28), 9
            ),
            LetterLine(uuid.uuid4(), org_b, LetterState.TO_ANSWER, None, date(2026, 10, 9), 2),
        ]
        speeds = [
            OrganizationSpeed(org_a, 6, 12),
            OrganizationSpeed(org_b, 2, None),
        ]
        sleeping = AgreementLine(uuid.uuid4(), True, 130)
        found = {
            each.key: each
            for each in answers(
                letters,
                speeds,
                [sleeping, AgreementLine(uuid.uuid4(), False, 3)],
                today=TODAY,
                min_letters=5,
            )
        }

        waiting = found[Question.NOT_ANSWERING]
        assert (waiting.count, waiting.groups[0].oldest_days) == (2, 20)
        to_answer = found[Question.TO_ANSWER]
        assert (to_answer.count, to_answer.overdue) == (2, 1)
        assert to_answer.nearest is not None and to_answer.nearest[2] == 8
        assert found[Question.SPEED].rows == (org_a,)
        assert found[Question.SPEED].little_data == 1
        assert found[Question.SLEEPING].oldest == (sleeping.id, 130)
