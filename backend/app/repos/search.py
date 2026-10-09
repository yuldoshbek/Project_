"""Read-модель поиска: один запрос на все разделы (CLAUDE.md, «Read-модель на экран»).

Каждый вид находок — ветка `UNION ALL` со своим пределом, а не отдельный заход в базу:
поиск зовут на каждый набранный знак, и девять запросов вместо одного — это девять
сетевых задержек до Neon на каждое касание клавиатуры.

Индексов под поиск нет намеренно: на объёмах ТЗ 9 (500 проектов, 5 000 задач, 2 000
поручений, 5 000 писем) «содержит» без индекса — это просмотр двенадцати тысяч коротких
строк, единицы миллисекунд. Триграммный индекс понадобится, если объёмы вырастут на порядок.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import (
    ColumnElement,
    SQLColumnExpression,
    String,
    case,
    false,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.selectable import Select

from app.domain.search import HitKind, like_pattern
from app.repos.models import (
    Agreement,
    Idea,
    IjroAssignment,
    IjroDocument,
    Letter,
    Organization,
    Preparation,
    Project,
    Task,
)

Text = SQLColumnExpression[str] | SQLColumnExpression[str | None]
"""Столбец с текстом — ORM-атрибут или выражение: поиск принимает оба."""


@dataclass(frozen=True, slots=True)
class Hit:
    kind: HitKind
    id: uuid.UUID
    title: str
    code: str | None
    context: str | None


def _folded(column: Text) -> ColumnElement[str]:
    """Столбец так, как его сравнивает поиск, — функцией `search_fold` (миграция 0010_search).

    Функция, а не выражение на месте: по ней построены триграммные индексы `ix_search_*`, и
    база берёт индекс, только когда запрос называет то же выражение.
    """
    return func.search_fold(column, type_=String)


def _matches(columns: Sequence[Text], spellings: Sequence[str]) -> ColumnElement[bool]:
    return or_(
        false(),
        *(
            _folded(column).like(like_pattern(text), escape="\\")
            for column in columns
            for text in spellings
        ),
    )


def _rank(
    code: Text | None,
    title: Text,
    spellings: Sequence[str],
) -> ColumnElement[int]:
    """Номер, набранный целиком, — первым; название, которое с запроса начинается, — вторым."""
    whens: list[tuple[ColumnElement[bool], int]] = []
    if code is not None:
        whens.append((or_(*(_folded(code) == text for text in spellings)), 0))
    whens.append((or_(*(_folded(title).like(f"{text}%") for text in spellings)), 1))
    return case(*whens, else_=2)


def _branch(
    kind: SQLColumnExpression[str],
    id_: SQLColumnExpression[uuid.UUID],
    title: Text,
    code: Text | None,
    context: Text | None,
    spellings: Sequence[str],
    limit: int,
) -> Select[tuple[str, uuid.UUID, str, str | None, str | None, int]]:
    rank = _rank(code, title, spellings).label("rank")
    searchable = [title] if code is None else [title, code]
    return (
        select(
            kind.label("kind"),
            id_.label("id"),
            title.label("title"),
            (code if code is not None else literal(None, String)).label("code"),
            (context if context is not None else literal(None, String)).label("context"),
            rank,
        )
        .where(_matches(searchable, spellings))
        .order_by(rank, title)
        .limit(limit)
    )


async def search(session: AsyncSession, spellings: Sequence[str], *, per_kind: int) -> list[Hit]:
    """Находки всех видов: по виду не больше `per_kind + 1` — лишняя говорит «есть ещё»."""
    limit = per_kind + 1
    owner = aliased(Project)
    branches = [
        _branch(
            literal(HitKind.PROGRAM.value),
            Project.id,
            Project.title,
            Project.code,
            None,
            spellings,
            limit,
        ).where(Project.is_multiyear),
        _branch(
            literal(HitKind.PROJECT.value),
            Project.id,
            Project.title,
            Project.code,
            None,
            spellings,
            limit,
        ).where(Project.is_multiyear.is_(False)),
        _branch(
            literal(HitKind.TASK.value),
            Task.id,
            Task.title,
            Task.code,
            owner.title,
            spellings,
            limit,
        ).outerjoin(owner, owner.id == Task.project_id),
        _branch(
            literal(HitKind.IJRO.value),
            IjroAssignment.id,
            IjroAssignment.content,
            IjroAssignment.code,
            IjroDocument.number_raw,
            spellings,
            limit,
        ).join(IjroDocument, IjroDocument.id == IjroAssignment.document_id),
        _branch(
            literal(HitKind.LETTER.value),
            Letter.id,
            Letter.subject,
            Letter.number,
            Organization.name,
            spellings,
            limit,
        ).join(Organization, Organization.id == Letter.organization_id),
        _branch(
            literal(HitKind.ORGANIZATION.value),
            Organization.id,
            Organization.name,
            Organization.short_name,
            None,
            spellings,
            limit,
        ),
        _branch(
            literal(HitKind.AGREEMENT.value),
            Agreement.id,
            Agreement.title,
            None,
            Organization.name,
            spellings,
            limit,
        ).join(Organization, Organization.id == Agreement.organization_id),
        _branch(literal(HitKind.IDEA.value), Idea.id, Idea.text, None, None, spellings, limit),
        _branch(
            literal(HitKind.PREPARATION.value),
            Preparation.id,
            Preparation.title,
            None,
            None,
            spellings,
            limit,
        ),
    ]
    # Ветка с LIMIT внутри UNION должна быть подзапросом — иначе предел лёг бы на всё
    # объединение, и девять видов делили бы шесть мест.
    subqueries = [branch.subquery() for branch in branches]
    union = select(*subqueries[0].c).union_all(*(select(*sub.c) for sub in subqueries[1:]))
    rows = (await session.execute(union)).all()
    # Порядок внутри вида задаётся здесь, а не ORDER BY ветки: порядок строк подзапроса
    # объединение не обязано сохранять.
    ordered = sorted(rows, key=lambda row: (int(row.rank), row.title.lower(), str(row.id)))
    return [
        Hit(kind=HitKind(row.kind), id=row.id, title=row.title, code=row.code, context=row.context)
        for row in ordered
    ]
