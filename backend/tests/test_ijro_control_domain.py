"""Правила раздела «Ижро» без базы: признак жизни, задача из поручения, вопросы."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import date

from app.domain.attention import Attention
from app.domain.ijro import DuePrecision, IjroState, LifeSource
from app.domain.ijro_control import (
    LifeSign,
    Limits,
    Line,
    Question,
    answers,
    interim_on,
    quiet_days,
    sign_of_life,
    suggest_people,
    task_due,
    task_title,
    workdays_before,
)

TODAY = date(2026, 10, 1)  # четверг
LIMITS = Limits(quiet_days=14, near_due_days=30, pace_window_days=90, min_closed_for_pace=3)
ORG = uuid.uuid4()


def line(**fields: object) -> Line:
    base = Line(
        id=uuid.uuid4(),
        document_id=uuid.UUID(int=1),
        state=IjroState.IN_PROGRESS,
        state_changed_on=date(2026, 9, 1),
        step=None,
        deviation=0,
        due_on=date(2026, 10, 20),
        due_precision=DuePrecision.EXACT,
        original_due_on=date(2026, 10, 20),
        extensions=0,
        extension_requested=False,
        responsible_person_id=None,
        responsible_raw="Каримов А.",
        lead_organization_id=None,
        is_co_executor=False,
        quiet=0,
        has_problem=False,
        problem_updated_on=None,
        tasks=1,
        first_seen_on=date(2026, 6, 1),
    )
    return replace(base, **fields)  # type: ignore[arg-type]


def answer_of(lines: list[Line], key: Question) -> object:
    found = answers(lines, today=TODAY, limits=LIMITS, documents=[], batch=None)
    return next(each for each in found if each.key is key)


class TestSignOfLife:
    def test_the_freshest_event_wins(self) -> None:
        sign = sign_of_life(
            [
                LifeSign(date(2026, 9, 20), LifeSource.CONTROL_MARK),
                LifeSign(date(2026, 9, 25), LifeSource.TASK_MOVEMENT),
            ]
        )
        assert sign == LifeSign(date(2026, 9, 25), LifeSource.TASK_MOVEMENT)

    def test_silence_without_events_counts_from_first_seen(self) -> None:
        assert quiet_days(None, first_seen_on=date(2026, 9, 1), today=TODAY) == 30

    def test_interim_only_for_long_deadlines(self) -> None:
        assert interim_on(first_seen_on=date(2026, 9, 1), due_on=date(2026, 11, 1)) is None
        assert interim_on(first_seen_on=date(2026, 1, 1), due_on=date(2026, 12, 31)) == date(
            2026, 7, 2
        )


class TestTaskFromAssignment:
    def test_three_workdays_skip_the_weekend(self) -> None:
        # От понедельника 12.10: пятница 09, четверг 08, среда 07 — выходные не в счёт.
        assert workdays_before(date(2026, 10, 12), 3) == date(2026, 10, 7)

    def test_due_only_for_an_exact_deadline(self) -> None:
        assert task_due(date(2026, 10, 12), DuePrecision.EXACT) == date(2026, 10, 7)
        assert task_due(date(2026, 12, 25), DuePrecision.END_OF_YEAR) is None
        assert task_due(date(2026, 11, 30), DuePrecision.MONTH) is None

    def test_title_is_the_first_sentence(self) -> None:
        content = "Дастур ишлаб чиқилсин. Вазирлар Маҳкамасига киритилсин."
        assert task_title(content) == "Дастур ишлаб чиқилсин"

    def test_a_long_title_is_cut_by_word(self) -> None:
        title = task_title("сўз " * 200)
        assert len(title) <= 300
        assert title.endswith("…")


class TestSuggestions:
    def test_by_surname_ignoring_initials(self) -> None:
        karimov, karimova, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        people = [(karimov, "Каримов А."), (karimova, "Каримова Д."), (other, "Юсупова Д.")]
        assert suggest_people("А.Каримов", people) == [karimov, karimova]

    def test_nothing_for_an_empty_spelling(self) -> None:
        assert suggest_people("  ", [(uuid.uuid4(), "Каримов А.")]) == []


class TestQuestions:
    def test_silent_needs_a_near_deadline(self) -> None:
        near = line(quiet=20, due_on=date(2026, 10, 25))
        far = line(quiet=40, due_on=date(2026, 12, 1))
        silent = answer_of([near, far], Question.SILENT)
        assert silent.rows == (near.id,)  # type: ignore[attr-defined]

    def test_foreign_skips_what_waits_for_the_leader(self) -> None:
        stuck = line(
            is_co_executor=True, lead_organization_id=ORG, step=Attention.BLOCKED_BY_OTHERS
        )
        asked = line(
            is_co_executor=True, lead_organization_id=ORG, step=Attention.AWAITING_DECISION
        )
        foreign = answer_of([stuck, asked], Question.FOREIGN)
        assert foreign.rows == (stuck.id,)  # type: ignore[attr-defined]

    def test_without_tasks_counts_only_exact_deadlines(self) -> None:
        exact = line(tasks=0)
        coarse = line(tasks=0, due_precision=DuePrecision.END_OF_YEAR)
        found = answer_of([exact, coarse], Question.WITHOUT_TASKS)
        assert (found.rows, found.total) == ((exact.id,), 1)  # type: ignore[attr-defined]

    def test_submitted_is_not_open_work(self) -> None:
        sent = line(state=IjroState.SUBMITTED, extension_requested=True, has_problem=True)
        assert answer_of([sent], Question.EXTENSION_REQUESTED).rows == ()  # type: ignore[attr-defined]
        assert answer_of([sent], Question.REPORT_UP).rows == ()  # type: ignore[attr-defined]

    def test_year_end_says_little_data_below_the_threshold(self) -> None:
        closed = [
            line(state=IjroState.REMOVED_FROM_CONTROL, state_changed_on=date(2026, 9, 20))
            for _ in range(2)
        ]
        found = answer_of([*closed, line()], Question.YEAR_END)
        assert found.verdict == "little_data"  # type: ignore[attr-defined]
        assert found.upcoming == 1  # type: ignore[attr-defined]
