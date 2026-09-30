"""Вопросы к руководителю и его решения — единственная запись, которую делает Пульт.

Вопрос ставит помощник, решает руководитель (ТЗ 3.7, допущение V12). Решение закрывает
все открытые вопросы по объекту: после ответа объект ждёт уже не руководителя.

Отмена — не правка задним числом, а кнопка «Отменить» сразу после касания: одно касание
на телефоне легко сделать по ошибке. Поэтому она живёт короткое окно `UNDO_WINDOW` и
доступна только автору. Позже решение не отменяется, а принимается новое: журнал решений
отвечает на вопрос «что руководитель решил», и тихо исчезнувшее решение на него лжёт.

В журнал изменений всё попадает само — обработчиками сессии (`app.services.audit`),
включая удаление при отмене: запись «решено и отменено через минуту» остаётся видна.

Вопрос заводит руководителю уведомление «ждёт вашего решения» в той же транзакции (V27);
пуш уходит после её фиксации (`app.api.transaction.after_commit`).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.decisions import TEXT_MAX_LENGTH, DecisionKind, DecisionState, DecisionTarget
from app.domain.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    RuleViolationError,
    check_version,
)
from app.domain.projects import validate_horizon
from app.domain.push import NotificationKind, question_key, question_payload
from app.repos import notifications as recipients
from app.repos import pult as read_model
from app.repos.models import LeaderDecision, LeaderQuestion, User
from app.services import notifications

UNDO_WINDOW = timedelta(minutes=10)
"""Сколько после действия работает «Отменить». Экран показывает кнопку восемь секунд;
десять минут на сервере — запас на медленную сеть и на повтор запроса, а не второе окно
для раздумий."""


async def _existing_target(
    session: AsyncSession, kind: str, target_id: uuid.UUID
) -> uuid.UUID | None:
    """Проверяет, что объект есть; возвращает его ответственного."""
    if kind not in {target.value for target in DecisionTarget}:
        raise RuleViolationError(f"Решение нельзя принять по объекту «{kind}»")
    exists, responsible = await read_model.target_responsible(session, (kind, target_id))
    if not exists:
        raise NotFoundError("Объект решения не найден: его могли удалить")
    return responsible


def _clean_text(text: str | None, *, required: bool) -> str | None:
    value = (text or "").strip()
    if required and not value:
        raise RuleViolationError("Напишите, что именно нужно решить")
    if len(value) > TEXT_MAX_LENGTH:
        raise RuleViolationError(f"Текст длиннее {TEXT_MAX_LENGTH} символов")
    return value or None


async def decide(
    session: AsyncSession,
    *,
    user: User,
    target_type: str,
    target_id: uuid.UUID,
    kind: DecisionKind,
    text: str | None,
    today: date,
    now: datetime,
) -> LeaderDecision:
    """Решение руководителя по объекту — одно касание на Пульте.

    Ответственный за исполнение — тот, кто держит объект: «поторопить» в одно касание не
    спрашивает, кого торопить. Решение без исполнения («утвердить», «вернуть»,
    «отклонить») закрыто в момент принятия.
    """
    responsible = await _existing_target(session, target_type, target_id)
    done = not kind.needs_execution

    decision = LeaderDecision(
        target_type=target_type,
        target_id=target_id,
        kind=kind.value,
        text=_clean_text(text, required=False),
        assignee_person_id=responsible if kind.needs_assignee else None,
        state=DecisionState.DONE.value if done else DecisionState.OPEN.value,
        done_on=today if done else None,
        decided_by=user.id,
    )
    session.add(decision)
    await session.flush()

    # Решение отвечает на все открытые вопросы по объекту разом: два вопроса по одной
    # вехе — это один вопрос, заданный дважды, а не два ожидания. Через объекты, а не
    # массовым UPDATE: массовая правка обходит журнал изменений (`app.services.audit`).
    open_questions = await session.scalars(
        select(LeaderQuestion).where(
            LeaderQuestion.target_type == target_type,
            LeaderQuestion.target_id == target_id,
            LeaderQuestion.closed_at.is_(None),
        )
    )
    for question in open_questions:
        question.closed_at = now
        question.decision_id = decision.id
    await session.flush()
    return decision


async def undo_decision(
    session: AsyncSession, *, user: User, decision_id: uuid.UUID, now: datetime
) -> None:
    """«Отменить» сразу после решения: вопросы, которые оно закрыло, снова открыты."""
    decision = await session.get(LeaderDecision, decision_id)
    if decision is None:
        raise NotFoundError("Решение не найдено")
    if decision.decided_by != user.id:
        raise PermissionDeniedError("Отменить решение может только тот, кто его принял")
    if now - decision.created_at > UNDO_WINDOW:
        raise RuleViolationError(
            "Отменить можно только сразу после решения. Сейчас примите новое решение"
        )

    reopened = await session.scalars(
        select(LeaderQuestion).where(LeaderQuestion.decision_id == decision.id)
    )
    for question in reopened:
        question.closed_at = None
        question.decision_id = None
    await session.flush()
    await session.delete(decision)


async def ask(
    session: AsyncSession,
    *,
    user: User,
    target_type: str,
    target_id: uuid.UUID,
    text: str,
) -> LeaderQuestion:
    """Вопрос помощника руководителю — ставит объект на ступень «ждёт решения».

    И заводит руководителю уведомление в той же транзакции: откат вопроса откатывает и его,
    а пуш о вопросе, которого нет, не уйдёт.
    """
    await _existing_target(session, target_type, target_id)
    question = LeaderQuestion(
        target_type=target_type,
        target_id=target_id,
        text=_clean_text(text, required=True),
        asked_by=user.id,
    )
    session.add(question)
    await session.flush()

    leader = await recipients.leader(session)
    if leader is not None:
        table = read_model.TARGET_TABLE.get(target_type, "")
        titles = await read_model.titles(session, [(table, target_id)])
        await notifications.record(
            session,
            user_id=leader.id,
            kind=NotificationKind.AWAITING_DECISION,
            dedup_key=question_key(question.id),
            payload=question_payload(
                question.id, title=titles.get((table, target_id)), text=question.text
            ),
            entity_type="question",
            entity_id=question.id,
        )
    return question


async def undo_question(
    session: AsyncSession, *, user: User, question_id: uuid.UUID, now: datetime
) -> None:
    """«Отменить» сразу после вопроса. На вопрос, на который уже ответили, — отказ."""
    question = await session.get(LeaderQuestion, question_id)
    if question is None:
        raise NotFoundError("Вопрос не найден")
    if question.asked_by != user.id:
        raise PermissionDeniedError("Отменить вопрос может только тот, кто его задал")
    if question.closed_at is not None:
        raise RuleViolationError("На вопрос уже ответили — отменять нечего")
    if now - question.created_at > UNDO_WINDOW:
        raise RuleViolationError("Отменить можно только сразу после вопроса")
    await session.delete(question)
    # Неотправленное уведомление уходит вместе с вопросом. Пуш, уже пришедший на телефон,
    # не отзывается: касание откроет сводку, где вопроса уже нет (ADR-0036).
    await notifications.withdraw(session, dedup_key=question_key(question.id))


async def _decision(session: AsyncSession, decision_id: uuid.UUID) -> LeaderDecision:
    decision = await session.get(LeaderDecision, decision_id)
    if decision is None:
        raise NotFoundError("Решение не найдено: его могли отменить")
    return decision


async def complete(
    session: AsyncSession, *, decision_id: uuid.UUID, version: int, today: date
) -> None:
    """Решение исполнено — из обхода «Управления» (ТЗ 3.7, допущение V20).

    Отмечает помощник: исполнение видно ему, а не тому, кто решал. Исполненное второй раз
    не отмечается — это устаревшая картина, а не новое событие.
    """
    decision = await _decision(session, decision_id)
    check_version(expected=version, actual=decision.version)
    if decision.state == DecisionState.DONE.value:
        raise ConflictError("Решение уже исполнено")
    decision.state = DecisionState.DONE.value
    decision.done_on = today
    await session.flush()


async def move_due(
    session: AsyncSession, *, decision_id: uuid.UUID, due_on: date, version: int
) -> None:
    """Новый срок исполнения решения — «перенести на неделю» в обходе."""
    decision = await _decision(session, decision_id)
    check_version(expected=version, actual=decision.version)
    if decision.state == DecisionState.DONE.value:
        raise ConflictError("Исполненное решение не переносят")
    validate_horizon(due_on)
    decision.due_on = due_on
    await session.flush()
