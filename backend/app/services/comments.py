"""Комментарии: сценарии использования.

Три вещи, которые здесь решаются и о которых легко не подумать.

**Комментарий к несуществующей записи не заводится.** Проверка стоит на создании, а не на
чтении: иначе в базе оседают реплики-сироты, которые не видно ни в одной ленте и которые
всплывут при первом же переносе данных.

**Правит и удаляет только автор.** Сегодня писать может один человек (ADR-0011), и
проверка выглядит лишней — но решение руководителя по проекту (ORB-062) ляжет в ту же
ленту за его подписью, и тогда «только автор» станет единственным, что мешает помощнику
переписать чужую резолюцию.

**Упоминание разбирается один раз, при сохранении.** И один раз извещает: правка реплики,
в которой то же имя осталось на месте, второго уведомления не порождает — за это отвечает
ключ повторной вставки (инвариант 6).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clock import now_utc
from app.domain.comments import CommentTarget, find_mentions, validate_body
from app.domain.errors import NotFoundError, PermissionDeniedError, RuleViolationError
from app.repos.models import Comment, Notification, Person, Project, Task, User

MENTION_KIND = "mention"

_TABLE: dict[CommentTarget, type[Project] | type[Task]] = {
    CommentTarget.PROJECT: Project,
    CommentTarget.TASK: Task,
}


@dataclass(slots=True)
class CommentDraft:
    entity_type: CommentTarget
    entity_id: uuid.UUID
    body: str


@dataclass(frozen=True, slots=True)
class CommentView:
    """Реплика вместе с тем, что о ней вычислено."""

    comment: Comment
    mentioned: list[Person]

    @property
    def is_deleted(self) -> bool:
        return self.comment.deleted_at is not None

    @property
    def body(self) -> str | None:
        """Текст или `None` у удалённой реплики.

        `None`, а не пустая строка: пустой текст — это текст, а отсутствующий говорит
        читателю «здесь было и удалено», ради чего мягкое удаление и заводилось.
        """
        return None if self.is_deleted else self.comment.body


async def target_exists(
    session: AsyncSession, entity_type: CommentTarget, entity_id: uuid.UUID
) -> bool:
    model = _TABLE[entity_type]
    found = await session.scalar(select(model.id).where(model.id == entity_id))
    return found is not None


async def get(session: AsyncSession, comment_id: uuid.UUID) -> Comment:
    comment = await session.get(Comment, comment_id)
    if comment is None:
        raise NotFoundError("Комментарий не найден")
    return comment


async def list_for(
    session: AsyncSession, entity_type: CommentTarget, entity_id: uuid.UUID
) -> list[CommentView]:
    """Лента одной записи, включая удалённые реплики.

    Удалённые не выбрасываются, а приходят без текста: пропуск в переписке делает соседние
    реплики непонятными, и читатель не может отличить «здесь ничего не было» от «здесь
    было и убрали».
    """
    if not await target_exists(session, entity_type, entity_id):
        raise NotFoundError("Запись не найдена")

    comments = list(
        await session.scalars(
            select(Comment)
            .where(Comment.entity_type == entity_type.value, Comment.entity_id == entity_id)
            .order_by(Comment.created_at)
        )
    )
    return await _with_mentions(session, comments)


async def create(session: AsyncSession, draft: CommentDraft, *, author: User) -> CommentView:
    body = _valid(draft.body)

    if not await target_exists(session, draft.entity_type, draft.entity_id):
        raise NotFoundError("Запись не найдена")

    comment = Comment(
        entity_type=draft.entity_type.value,
        entity_id=draft.entity_id,
        author_id=author.id,
        body=body,
    )
    session.add(comment)
    await session.flush()

    await _notify_mentioned(session, comment, author=author)
    return (await _with_mentions(session, [comment]))[0]


async def update(
    session: AsyncSession, comment_id: uuid.UUID, body: str, *, author: User
) -> CommentView:
    comment = await _own(session, comment_id, author=author)
    if comment.deleted_at is not None:
        raise RuleViolationError(
            "Удалённый комментарий не правится",
            detail="восстановление удалённых реплик не предусмотрено",
        )

    comment.body = _valid(body)
    comment.edited_at = now_utc()
    await session.flush()

    await _notify_mentioned(session, comment, author=author)
    return (await _with_mentions(session, [comment]))[0]


async def delete(session: AsyncSession, comment_id: uuid.UUID, *, author: User) -> None:
    """Мягкое удаление: строка остаётся, текст перестаёт выдаваться.

    Повторное удаление — не ошибка, а тот же результат: человек нажал дважды, и второй
    отказ ему ничего не объясняет.
    """
    comment = await _own(session, comment_id, author=author)
    if comment.deleted_at is None:
        comment.deleted_at = now_utc()
        await session.flush()


async def delete_for(
    session: AsyncSession, entity_type: CommentTarget, entity_id: uuid.UUID
) -> None:
    """Убирает обсуждение вместе с записью, к которой оно относилось.

    Внешним ключом это не выражается — `entity_id` указывает то на проекты, то на задачи,
    — поэтому целостность держит вызов отсюда. Забыть его значит оставить в базе реплики,
    которых не видно ни в одной ленте.
    """
    for comment in await session.scalars(
        select(Comment).where(
            Comment.entity_type == entity_type.value, Comment.entity_id == entity_id
        )
    ):
        await session.delete(comment)
    await session.flush()


async def _own(session: AsyncSession, comment_id: uuid.UUID, *, author: User) -> Comment:
    comment = await get(session, comment_id)
    if comment.author_id != author.id:
        raise PermissionDeniedError(
            "Чужой комментарий изменить нельзя",
            detail="править и удалять реплику может только её автор",
        )
    return comment


def _valid(body: str) -> str:
    try:
        return validate_body(body)
    except ValueError as error:
        raise RuleViolationError("Комментарий не годится", detail=str(error)) from error


async def resolve_mentions(session: AsyncSession, body: str) -> list[Person]:
    """Сотрудники, названные в тексте через «собаку».

    Совпадение по **части ФИО целиком**: «@Рахимов» находит «Рахимов Рустам Акмалович», а
    «@Рах» не находит никого. Поиск по началу слова выглядел бы удобнее ровно до первого
    «@Кар», который совпал бы и с Каримовым, и с Каримовой.

    Имя, подходящее **нескольким**, не разбирается ни в кого. Однофамильцы в агентстве
    есть, и предупредить не того человека о не его проекте хуже, чем не предупредить
    никого: первое выглядит как утечка, второе — как забывчивость автора, который видит
    свой текст и может дописать имя.
    """
    found: dict[uuid.UUID, Person] = {}

    for token in find_mentions(body):
        matched = list(
            await session.scalars(
                select(Person).where(
                    Person.is_active.is_(True),
                    or_(
                        func.lower(Person.full_name) == token.lower(),
                        func.lower(Person.full_name).like(f"{token.lower()} %"),
                        func.lower(Person.full_name).like(f"% {token.lower()}"),
                        func.lower(Person.full_name).like(f"% {token.lower()} %"),
                    ),
                )
            )
        )
        if len(matched) == 1:
            found.setdefault(matched[0].id, matched[0])

    return list(found.values())


async def _with_mentions(session: AsyncSession, comments: list[Comment]) -> list[CommentView]:
    views = []
    for comment in comments:
        mentioned = [] if comment.deleted_at else await resolve_mentions(session, comment.body)
        views.append(CommentView(comment=comment, mentioned=mentioned))
    return views


async def _notify_mentioned(session: AsyncSession, comment: Comment, *, author: User) -> None:
    """Извещает о каждом упоминании — по одному разу.

    Извещается **второй пользователь**, а не упомянутый: сотрудники в систему не входят,
    и показать им внутри неё нечего (Q24, ADR-0011). Кого упомянули, при этом
    сохраняется — чтобы доставку можно было изменить, не потеряв данные.

    Себе уведомлений не шлют: автор только что написал этот текст.
    """
    mentioned = await resolve_mentions(session, comment.body)
    if not mentioned:
        return

    recipients = list(
        await session.scalars(select(User).where(User.id != author.id, User.is_active.is_(True)))
    )
    if not recipients:
        return

    for person in mentioned:
        for recipient in recipients:
            key = f"comment:{comment.id}:mention:{person.id}:user:{recipient.id}"
            exists = await session.scalar(
                select(Notification.id).where(Notification.dedup_key == key)
            )
            if exists is not None:
                continue

            session.add(
                Notification(
                    user_id=recipient.id,
                    kind=MENTION_KIND,
                    entity_type=comment.entity_type,
                    entity_id=comment.entity_id,
                    dedup_key=key,
                    payload={
                        "comment_id": str(comment.id),
                        "person_id": str(person.id),
                        "person_name": person.full_name,
                        "author_id": str(author.id),
                    },
                )
            )

    await session.flush()
