"""Привоз контрольной таблицы «Ижро»: предпросмотр и применение (ТЗ 3.3, 7).

Две фазы, а не режим: предпросмотр — партия `preview` с построчным отчётом в базе
(`IjroImport.report`), применение — отдельный запрос по ней. Помощник может уйти,
вернуться и показать разбор руководителю до того, как в реестр попадёт хоть одна строка.

Форма — договор экрана «Загрузка» (`frontend/src/sections/ijro/model.ts`: `Preview`,
`ApplyChoices`, `ApplyResult`), утверждённого 30.09.2026.

**Привоз меняет только поля источника** (инвариант 4): содержание, механизм, срок как в
таблице, написание ответственного, головного исполнителя, графу состояния источника.
Этап, проблема, предложение, «запрошено продление», лента и связи — наши, и их привоз не
трогает никогда; это проверяется тестом.

**Перенос срока записывается только подтверждённый человеком** (ТЗ 7) и попадает в
историю продлений; неподтверждённый ждёт в отчёте партии. **Написание ФИО сопоставляет
человек**, выбор запоминается псевдонимом. **Та же таблица второй раз ничего не меняет**:
партия опознаётся по sha256 файла.

Исходный файл пока не сохраняется: порта `FileStorage` ещё нет — он приходит с разделом
«Файлы»; до тех пор у партии остаются имя, отпечаток и построчный отчёт.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import docx
from app.domain.clock import local_date
from app.domain.errors import NotFoundError, RuleViolationError
from app.domain.ijro import (
    AliasSource,
    ExtensionKind,
    IjroSource,
    IjroState,
    ImportState,
    band_sort_key,
    normalize_person_name,
)
from app.domain.ijro_control import suggest_people
from app.domain.ijro_import import (
    BadRow,
    Change,
    ChangeClass,
    ParsedRow,
    compare,
    guess_source,
    normalize_organization,
    organization_kind,
    parse_table,
)
from app.repos import ijro as read_model
from app.repos.models import (
    IjroAssignment,
    IjroDocument,
    IjroExtension,
    IjroImport,
    IjroOrgAlias,
    IjroPersonAlias,
    Organization,
    Person,
    User,
)
from app.services.codes import add_with_code, next_code

CODE_PREFIX = "IJR"
CODE_DIGITS = 3


@dataclass(frozen=True, slots=True)
class PreviewView:
    batch_id: uuid.UUID
    file: str
    source: str
    table_year: int
    table_on: date
    counts: dict[str, int]
    rows: list[dict[str, Any]]
    already_applied_on: date | None


@dataclass(frozen=True, slots=True)
class Choices:
    due_moves: dict[str, ExtensionKind] = field(default_factory=dict)
    aliases: dict[str, uuid.UUID] = field(default_factory=dict)
    removed: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ApplyView:
    outcome: str
    created: int = 0
    changed: int = 0
    vanished: int = 0
    removed: int = 0
    extensions: int = 0
    pending_extensions: int = 0
    applied_on: date | None = None


def _counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {name.value: sum(row["class"] == name.value for row in rows) for name in ChangeClass}


def _data(row: ParsedRow) -> dict[str, Any]:
    """Поля источника строки — то, что применение запишет, не перечитывая файл."""
    return {
        "document_raw": row.document_raw,
        "document_code": row.document_code,
        "code_norm": row.code_norm,
        "kind": row.kind.value,
        "issued_on": row.issued_on.isoformat() if row.issued_on else None,
        "band": row.band,
        "content": row.content,
        "mechanism": row.mechanism,
        "due_raw": row.due_raw,
        "due_on": row.due_on.isoformat() if row.due_on else None,
        "due_precision": row.due_precision.value,
        "due_year_source": row.due_year_source.value if row.due_year_source else None,
        "block_label": row.block_label,
        "responsible_raw": row.responsible_raw,
        "responsible_ours": row.responsible_ours,
        "lead_raw": row.lead_raw,
        "state_raw": row.state_raw,
    }


def _day(value: Any) -> date | None:
    return date.fromisoformat(value) if value else None


async def preview(
    session: AsyncSession,
    *,
    user: User,
    content: bytes,
    filename: str,
    source: IjroSource | None,
    table_year: int | None,
    now: datetime,
    zone: ZoneInfo,
) -> PreviewView:
    """Разбор таблицы и сверка с реестром — без единой записи в реестр."""
    today = local_date(now, zone)
    name = filename.strip()[:400] or "таблица.docx"
    digest = hashlib.sha256(content).hexdigest()
    applied = await read_model.applied_import(session, digest)
    if applied is not None:
        return PreviewView(
            batch_id=applied.id,
            file=name,
            source=applied.source or (source or IjroSource.PA).value,
            table_year=applied.table_year or today.year,
            table_on=applied.table_on or today,
            counts={each.value: 0 for each in ChangeClass},
            rows=[],
            already_applied_on=local_date(applied.applied_at or now, zone),
        )

    chosen = source or guess_source(name)
    if chosen is None:
        raise RuleViolationError("Выберите источник таблицы: АП, Кабмин или законодательство")
    document = docx.read(content)
    parsed = parse_table(
        document.paragraphs,
        [[row.cells for row in table] for table in document.tables],
        fallback_year=today.year,
        year=table_year,
    )
    registry = await read_model.import_registry(session)
    comparison = compare(parsed.rows, [each.existing for each in registry], source=chosen.value)
    by_id = {each.existing.id: each for each in registry}
    people = await read_model.people(session)
    aliases = await _people_keys(session, people)
    names = dict(people)

    def unmatched(change: Change) -> dict[str, Any] | None:
        ours = change.row.responsible_ours
        if not ours or normalize_person_name(ours) in aliases:
            return None
        known = by_id.get(change.assignment_id) if change.assignment_id else None
        if (
            known is not None
            and known.responsible_person_id is not None
            and known.existing.responsible_raw == change.row.responsible_raw
        ):
            return None
        return {
            "raw": ours,
            "suggestions": [
                {"id": str(person), "name": names[person]}
                for person in suggest_people(ours, people)
            ],
        }

    rows: list[dict[str, Any]] = []
    for change in comparison.changes:
        row = change.row
        rows.append(
            {
                "id": str(row.index),
                "class": change.kind.value,
                "assignment_id": str(change.assignment_id) if change.assignment_id else None,
                "document_code": row.document_code,
                "band": row.band,
                "content": row.content,
                "diff": (
                    {"field": change.diff[0], "from": change.diff[1], "to": change.diff[2]}
                    if change.diff
                    else None
                ),
                "due_move": (
                    {
                        "from": change.due_from.isoformat(),
                        "to": row.due_on.isoformat(),
                        "suggested_kind": (change.suggested or ExtensionKind.EXTENSION).value,
                    }
                    if change.due_from and row.due_on
                    else None
                ),
                "unmatched": unmatched(change),
                "raw": None,
                "data": _data(row),
            }
        )
    for assignment_id in comparison.vanished:
        known = by_id[assignment_id]
        rows.append(
            {
                "id": f"v-{assignment_id}",
                "class": ChangeClass.VANISHED.value,
                "assignment_id": str(assignment_id),
                "document_code": known.document_code,
                "band": known.existing.band,
                "content": known.existing.content,
                "diff": None,
                "due_move": None,
                "unmatched": None,
                "raw": None,
            }
        )
    rows += [_bad(each) for each in parsed.bad]

    counts = _counts(rows)
    batch = IjroImport(
        filename=name,
        sha256=digest,
        uploaded_by=user.id,
        uploaded_at=now,
        table_on=today,
        source=chosen.value,
        table_year=parsed.table_year,
        rows_total=len(parsed.rows) + len(parsed.bad),
        rows_new=counts[ChangeClass.NEW.value],
        rows_changed=counts[ChangeClass.TEXT_CHANGED.value]
        + counts[ChangeClass.RESPONSIBLE_CHANGED.value]
        + counts[ChangeClass.DUE_MOVED.value],
        rows_unrecognized=counts[ChangeClass.UNRECOGNIZED.value],
        state=ImportState.PREVIEW.value,
        report={"counts": counts, "rows": rows},
    )
    session.add(batch)
    await session.flush()
    return PreviewView(
        batch_id=batch.id,
        file=name,
        source=chosen.value,
        table_year=parsed.table_year,
        table_on=today,
        counts=counts,
        rows=[{key: value for key, value in row.items() if key != "data"} for row in rows],
        already_applied_on=None,
    )


def _bad(row: BadRow) -> dict[str, Any]:
    return {
        "id": f"u-{row.index}",
        "class": ChangeClass.UNRECOGNIZED.value,
        "assignment_id": None,
        "document_code": None,
        "band": None,
        "content": "",
        "diff": None,
        "due_move": None,
        "unmatched": None,
        "raw": row.raw,
        "reason": row.reason,
    }


async def _people_keys(
    session: AsyncSession, people: list[tuple[uuid.UUID, str]]
) -> dict[str, uuid.UUID]:
    """Написание → сотрудник: подтверждённые псевдонимы и ФИО справочника буква в букву.

    Совпадение с ФИО после механического приведения (пробелы, `И.Фамилия`, латинские
    омоглифы) сводится само — это ровно та граница, которую ADR-0025 отводит
    автоматике. Всё, что сложнее («Ш. Арибжанов» против «А. Арибжанова»), подтверждает
    человек. Два сотрудника с одним написанием — не совпадение, а вопрос к человеку.
    """
    keys: dict[str, uuid.UUID] = {}
    taken: set[str] = set()
    for person_id, name in people:
        key = normalize_person_name(name)
        if key in keys:
            taken.add(key)
        keys[key] = person_id
    for key in taken:
        del keys[key]
    keys.update(await read_model.person_aliases(session))
    return keys


class _Resolver:
    """Сотрудники и ведомства по написанию — псевдонимы, справочник, новые ведомства."""

    def __init__(
        self,
        session: AsyncSession,
        people: dict[str, uuid.UUID],
        organizations: dict[str, uuid.UUID],
    ) -> None:
        self.session = session
        self.people = people
        self.organizations = organizations

    def person(self, ours: str) -> uuid.UUID | None:
        return self.people.get(normalize_person_name(ours)) if ours else None

    async def organization(self, raw: str | None) -> uuid.UUID | None:
        """Головной исполнитель; незнакомое ведомство заводится и запоминается псевдонимом.

        Заводится, а не ждёт человека: без ведомства строка соисполнения нарушила бы правило
        «соисполнитель называет головного» (`co_executor_has_a_lead_organization`), а ошибка
        в ведомстве дешевле ошибки в человеке — ведомство только группирует «письмо или
        звонок» и правится в «Управлении».
        """
        if not raw:
            return None
        key = normalize_organization(raw)
        if key in self.organizations:
            return self.organizations[key]
        organization = Organization(name=raw[:300], kind=organization_kind(raw))
        self.session.add(organization)
        await self.session.flush()
        self.session.add(
            IjroOrgAlias(
                alias_norm=key[:300], organization_id=organization.id, source=AliasSource.AUTO.value
            )
        )
        self.organizations[key] = organization.id
        return organization.id


async def _resolver(session: AsyncSession) -> _Resolver:
    organizations: dict[str, uuid.UUID] = {}
    for org_id, name, short in await read_model.organization_keys(session):
        organizations.setdefault(normalize_organization(name), org_id)
        if short:
            organizations.setdefault(normalize_organization(short), org_id)
    organizations.update(await read_model.organization_aliases(session))
    people = await read_model.people(session)
    return _Resolver(session, await _people_keys(session, people), organizations)


def _source_fields(assignment: IjroAssignment, data: dict[str, Any]) -> bool:
    """Поля источника из строки таблицы; возвращает, изменилось ли видимое человеку.

    Видимое — содержание, механизм, написание ответственного: по ним строка попадает в
    «что привезли последней таблицей». Сырой срок, разделитель и графа состояния
    обновляются молча — это след источника, а не новость для руководителя.
    """
    visible = {
        "content": data["content"],
        "mechanism": data["mechanism"],
        "responsible_raw": data["responsible_raw"],
    }
    quiet = {
        "band_sort": band_sort_key(data["band"]),
        "due_raw": data["due_raw"],
        "block_label": data["block_label"],
        "source_state_raw": data["state_raw"],
    }
    changed = False
    for name, value in (visible | quiet).items():
        if getattr(assignment, name) != value:
            setattr(assignment, name, value)
            changed = changed or name in visible
    return changed


async def apply(
    session: AsyncSession,
    *,
    user: User,
    batch_id: uuid.UUID,
    choices: Choices,
    now: datetime,
    zone: ZoneInfo,
) -> ApplyView:
    """Применение партии: только поля источника и только подтверждённые переносы."""
    batch = await session.get(IjroImport, batch_id)
    if batch is None:
        raise NotFoundError("Партия привоза не найдена: загрузите таблицу заново")
    applied = await read_model.applied_import(session, batch.sha256)
    if applied is not None:
        return ApplyView(
            outcome="already_applied",
            applied_on=local_date(applied.applied_at or now, zone),
        )
    if batch.state != ImportState.PREVIEW.value:
        raise RuleViolationError("Эту партию уже отклонили: загрузите таблицу заново")

    report: dict[str, Any] = dict(batch.report or {})
    rows: list[dict[str, Any]] = list(report.get("rows", []))
    by_row = {row["id"]: row for row in rows}
    resolve = await _resolver(session)

    # Подтверждённые сопоставления — сначала: они ставят сотрудника и новым строкам, и
    # всем остальным строкам партии с тем же написанием.
    written: dict[str, IjroPersonAlias] = {}
    for row_id, person_id in choices.aliases.items():
        row = by_row.get(row_id)
        if row is None or not row.get("data"):
            raise RuleViolationError("Сопоставление относится к строке, которой нет в партии")
        person = await session.get(Person, person_id)
        if person is None or not person.is_active:
            raise RuleViolationError("Сотрудник не найден в справочнике")
        key = normalize_person_name(row["data"]["responsible_ours"])
        alias = written.get(key) or await _alias(session, key)
        if alias is None:
            alias = IjroPersonAlias(alias_norm=key, person_id=person_id)
            session.add(alias)
        alias.person_id = person_id
        alias.source = AliasSource.MANUAL.value
        written[key] = alias
        resolve.people[key] = person_id

    today = local_date(now, zone)
    created: list[uuid.UUID] = []
    changed: list[uuid.UUID] = []
    seen: list[uuid.UUID] = []
    pending: list[dict[str, Any]] = []
    extensions = removed = vanished = 0
    documents: dict[str, IjroDocument] = {}

    for row in rows:
        kind = ChangeClass(row["class"])
        data = row.get("data")
        if kind is ChangeClass.UNRECOGNIZED:
            continue
        if kind is ChangeClass.VANISHED:
            vanished += 1
            if row["id"] in choices.removed:
                assignment = await _assignment(session, row["assignment_id"])
                if assignment.state != IjroState.REMOVED_FROM_CONTROL.value:
                    assignment.state = IjroState.REMOVED_FROM_CONTROL.value
                    assignment.state_changed_at = now
                    removed += 1
            continue
        assert data is not None
        lead = await resolve.organization(data["lead_raw"])
        if kind is ChangeClass.NEW:
            document = documents.get(data["code_norm"]) or await _document(
                session, data, batch.source or IjroSource.PA.value
            )
            documents[data["code_norm"]] = document
            due_on = _day(data["due_on"])
            assignment = IjroAssignment(
                document_id=document.id,
                band=data["band"],
                band_sort=band_sort_key(data["band"]),
                content=data["content"],
                mechanism=data["mechanism"],
                due_on=due_on,
                original_due_on=due_on,
                due_raw=data["due_raw"],
                due_precision=data["due_precision"],
                due_year_source=data["due_year_source"],
                block_label=data["block_label"],
                responsible_raw=data["responsible_raw"],
                responsible_person_id=resolve.person(data["responsible_ours"]),
                lead_organization_id=lead,
                is_co_executor=lead is not None,
                state=IjroState.NOT_STARTED.value,
                state_changed_at=now,
                source_state_raw=data["state_raw"],
                import_batch_id=batch.id,
                first_seen_at=now,
                last_seen_in_import_at=now,
            )
            await add_with_code(
                session,
                assignment,
                assign=lambda: next_code(
                    session,
                    column=IjroAssignment.code,
                    prefix=CODE_PREFIX,
                    digits=CODE_DIGITS,
                    today=today,
                ),
            )
            created.append(assignment.id)
            continue

        assignment = await _assignment(session, row["assignment_id"])
        seen.append(assignment.id)
        if kind is ChangeClass.UNCHANGED and assignment.responsible_person_id is not None:
            # Без изменений — без правки: иначе каждый привоз поднимал бы версию строки ради
            # служебных полей, и открытая карточка получала бы отказ «запись изменили».
            continue
        if kind is ChangeClass.DUE_MOVED:
            confirmed = choices.due_moves.get(row["id"])
            if confirmed is None:
                pending.append(
                    {
                        "assignment_id": row["assignment_id"],
                        "from": row["due_move"]["from"],
                        "to": row["due_move"]["to"],
                    }
                )
                continue
            new_due = _day(data["due_on"])
            assert new_due is not None and assignment.due_on is not None
            session.add(
                IjroExtension(
                    assignment_id=assignment.id,
                    due_from=assignment.due_on,
                    due_to=new_due,
                    kind=confirmed.value,
                    import_batch_id=batch.id,
                )
            )
            assignment.due_on = new_due
            assignment.due_precision = data["due_precision"]
            assignment.due_year_source = data["due_year_source"]
            extensions += 1
        touched = _source_fields(assignment, data)
        if kind is ChangeClass.RESPONSIBLE_CHANGED or assignment.responsible_person_id is None:
            # Сменилось написание — сотрудник по новому написанию, даже пустой: прежний
            # сопоставлен с другим человеком. Без смены — только дополняем пустое.
            match = resolve.person(data["responsible_ours"])
            if assignment.responsible_person_id != match and (
                match is not None or kind is ChangeClass.RESPONSIBLE_CHANGED
            ):
                assignment.responsible_person_id = match
                touched = True
        if assignment.lead_organization_id != lead:
            assignment.lead_organization_id = lead
            assignment.is_co_executor = lead is not None
            touched = True
        if touched or kind is ChangeClass.DUE_MOVED:
            changed.append(assignment.id)

    await session.flush()
    if seen:
        # «Видели в таблице» — служебная отметка, а не правка: мимо ORM, без версии и без
        # журнала. Иначе каждый привоз поднимал бы версию всех строк, и открытая карточка
        # получала бы отказ «запись изменили» без единого изменения.
        await session.execute(
            update(IjroAssignment)
            .where(IjroAssignment.id.in_(seen))
            .values(last_seen_in_import_at=now)
            .execution_options(synchronize_session=False)
        )

    batch.state = ImportState.APPLIED.value
    batch.applied_at = now
    batch.report = {
        **report,
        "created": [str(each) for each in created],
        "changed": [str(each) for each in changed],
        "vanished": vanished,
        "pending": pending,
    }
    nothing = not (created or changed or removed or extensions or pending or vanished)
    return ApplyView(
        outcome="no_changes" if nothing else "applied",
        created=len(created),
        changed=len(changed),
        vanished=vanished,
        removed=removed,
        extensions=extensions,
        pending_extensions=len(pending),
    )


async def _alias(session: AsyncSession, key: str) -> IjroPersonAlias | None:
    found: IjroPersonAlias | None = await session.scalar(
        select(IjroPersonAlias).where(IjroPersonAlias.alias_norm == key)
    )
    return found


async def _assignment(session: AsyncSession, assignment_id: str) -> IjroAssignment:
    found = await session.get(IjroAssignment, uuid.UUID(assignment_id))
    if found is None:
        raise NotFoundError("Поручение из партии удалили: загрузите таблицу заново")
    return found


async def _document(session: AsyncSession, data: dict[str, Any], source: str) -> IjroDocument:
    found = await read_model.document_by_code(session, data["code_norm"])
    if found is not None:
        return found
    document = IjroDocument(
        code_norm=data["code_norm"],
        kind=data["kind"],
        number_raw=data["document_code"],
        issued_on=_day(data["issued_on"]),
        source=source,
        title_raw=data["document_raw"],
    )
    session.add(document)
    await session.flush()
    return document
