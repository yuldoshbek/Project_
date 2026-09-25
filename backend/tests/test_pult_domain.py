"""Правила Пульта над журналом: что считать изменением и что — переносом срока.

Без базы: записи журнала собираются руками, как их пишет `app.services.audit`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.domain.pult import AuditEntry, ChangeKind, classify, deadline_moves

TASHKENT = ZoneInfo("Asia/Tashkent")
AT = datetime(2026, 9, 25, 9, 0, tzinfo=UTC)


def entry(
    entity_type: str, action: str, changes: dict[str, object], entity_id: uuid.UUID | None = None
) -> AuditEntry:
    return AuditEntry(
        occurred_at=AT,
        entity_type=entity_type,
        entity_id=entity_id or uuid.uuid4(),
        action=action,
        changes=changes,
    )


class TestClassify:
    def test_closed_task_and_moved_deadline_in_one_edit(self) -> None:
        """Одна правка — два изменения: задачу закрыли и сдвинули ей срок."""
        found = classify(
            entry(
                "tasks",
                "updated",
                {
                    "status": {"from": "in_progress", "to": "done"},
                    "due_at": {
                        "from": "2026-09-24T13:00:00+00:00",
                        "to": "2026-09-30T13:00:00+00:00",
                    },
                },
            ),
            TASHKENT,
        )

        assert [change.kind for change in found] == [ChangeKind.CLOSED, ChangeKind.DEADLINE_MOVED]
        assert found[1].moved == (date(2026, 9, 24), date(2026, 9, 30))

    def test_task_deadline_is_read_in_tashkent(self) -> None:
        """Срок задачи 25.09 22:00 UTC — это 26.09 по Ташкенту (инвариант 8)."""
        found = classify(
            entry(
                "tasks",
                "updated",
                {
                    "due_at": {
                        "from": "2026-09-20T10:00:00+00:00",
                        "to": "2026-09-25T22:00:00+00:00",
                    }
                },
            ),
            TASHKENT,
        )
        assert found[0].moved == (date(2026, 9, 20), date(2026, 9, 26))

    def test_milestones_created_with_a_project_are_not_news(self) -> None:
        """Вехи подставляет шаблон: десять «новых вех» заслонили бы один новый проект."""
        assert classify(entry("milestones", "created", {}), TASHKENT) == []
        assert classify(entry("projects", "created", {}), TASHKENT)[0].kind is ChangeKind.CREATED

    def test_passed_milestone_and_done_decision(self) -> None:
        passed = classify(
            entry("milestones", "updated", {"is_passed": {"from": False, "to": True}}), TASHKENT
        )
        done = classify(
            entry("leader_decisions", "updated", {"state": {"from": "open", "to": "done"}}),
            TASHKENT,
        )

        assert passed[0].kind is ChangeKind.MILESTONE_PASSED
        assert done[0].kind is ChangeKind.DECISION_DONE

    def test_unrelated_edit_is_not_a_change(self) -> None:
        assert (
            classify(entry("projects", "updated", {"title": {"from": "а", "to": "б"}}), TASHKENT)
            == []
        )


class TestDeadlineMoves:
    def test_only_postponements_count(self) -> None:
        """Перенос — сдвиг позже. Подтянутый срок — не ответ на «держим ли мы сроки»."""
        item = uuid.uuid4()
        moves = deadline_moves(
            [
                entry(
                    "projects",
                    "updated",
                    {"due_on": {"from": "2026-09-01", "to": "2026-09-08"}},
                    item,
                ),
                entry(
                    "projects",
                    "updated",
                    {"due_on": {"from": "2026-09-08", "to": "2026-09-15"}},
                    item,
                ),
                entry(
                    "projects", "updated", {"due_on": {"from": "2026-10-10", "to": "2026-10-01"}}
                ),
            ],
            zone=TASHKENT,
            period_days=30,
            top=5,
        )

        assert (moves.moves, moves.total_shift_days) == (2, 14)
        assert moves.items[0].entity_id == item
        assert moves.items[0].moves == 2

    def test_most_postponed_first_and_list_is_capped(self) -> None:
        entries = [
            entry(
                "tasks",
                "updated",
                {
                    "due_at": {
                        "from": "2026-09-01T10:00:00+00:00",
                        "to": f"2026-09-{d:02d}T10:00:00+00:00",
                    }
                },
            )
            for d in range(2, 10)
        ]
        moves = deadline_moves(entries, zone=TASHKENT, period_days=30, top=3)

        assert len(moves.items) == 3
        shifts = [item.shift_days for item in moves.items]
        assert shifts == sorted(shifts, reverse=True)
        assert moves.moves == 8, "в счёт идут все переносы, а не только показанные"
