"""Вымышленные данные для разработки и превью — тот же набор, что на утверждённом экране.

    uv run python -m app.demo

Экран Пульта заказчик утвердил на вымышленных данных (25.09.2026). Здесь те же люди,
проекты и строки, но в базе: API считает их тем же кодом, что будет считать настоящие.
Критерий блока 0 «в демо — вымышленные данные» (перенесён в блок 1) закрывается этим же.

**В рабочем контуре не запускается никогда** (инвариант 11): отказ по `ORBITA_ENV`, а не
по доброй воле того, кто запускает. Повторный запуск ничего не добавляет: если проекты
уже есть, команда останавливается.

Две транзакции, а не одна. Первая заводит всё, что было «до прошлого визита», и ставит
отметку визита обоим пользователям. Вторая делает то, что случилось «после»: переносит
сроки, проходит веху, закрывает задачу, заводит проект. Так «С прошлого визита» и «Держим
ли мы свои сроки?» читают настоящий журнал изменений, а не заготовленный список.

Люди выдуманы; организации — только в роли партнёра по вымышленному проекту.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.clock import local_date
from app.domain.decisions import DecisionKind, DecisionState
from app.domain.dictionaries import OrganizationKind, OrganizationRole, ProjectStatus, TaskStatus
from app.repos.database import dispose_database, init_database, session_scope
from app.repos.models import (
    LeaderDecision,
    LeaderQuestion,
    Milestone,
    Organization,
    Person,
    Project,
    ProjectOrganization,
    ProjectTypeRef,
    Task,
    TaskTypeRef,
    User,
)
from app.services import audit as _audit  # noqa: F401 — журнал изменений включается импортом
from app.settings import get_settings

logger = structlog.get_logger(__name__)

PEOPLE = {
    "karimov": "Каримов А.",
    "yusupova": "Юсупова Д.",
    "rakhimov": "Рахимов Ш.",
    "tursunov": "Турсунов Б.",
    "abdullaeva": "Абдуллаева Н.",
}

PARTNER = "Министерство экологии"


@dataclass(frozen=True, slots=True)
class P:
    key: str
    type: str
    title: str
    who: str
    due: int
    created: int
    original: int | None = None


@dataclass(frozen=True, slots=True)
class T:
    key: str
    project: str | None
    title: str
    who: str
    due: int
    created: int
    kind: str = "other"


@dataclass(frozen=True, slots=True)
class M:
    key: str
    project: str
    title: str
    due: int
    order: int


PROJECTS = [
    P("mission", "satellite_mission", "Спутниковая миссия «Навоий-2»", "karimov", 200, 60),
    P("geodata", "regulation", "Постановление о порядке обмена геоданными", "yusupova", 40, 50),
    P("drought", "monitoring_cycle", "Цикл мониторинга: засуха-2026", "rakhimov", 120, 60),
    P("portal", "platform", "Геопортал агентства", "tursunov", 150, 70),
    P("crops", "industry_pilot", "Пилот: мониторинг посевов", "abdullaeva", 90, 40),
    P("standard", "standard", "Стандарт на снимки ДЗЗ", "yusupova", 60, 30),
    P("interns", "staff_education", "Кадры: стажировки в Центре мониторинга", "abdullaeva", 6, 6),
    P(
        "station",
        "international",
        "Приём наземной станции по соглашению о сотрудничестве",
        "rakhimov",
        61,
        23,
    ),
    # Головное ведомство чужое, и с его стороны три недели тишины — «зависит от чужих».
    # Станция для этого не годится: перенос её срока — тоже движение, и она оживает.
    P(
        "air",
        "international",
        "Совместная программа наблюдения за качеством воздуха",
        "yusupova",
        100,
        25,
    ),
    P(
        "aerial",
        "service_order",
        "Заказ услуги: аэрофотосъёмка Ферганской долины",
        "tursunov",
        90,
        21,
    ),
    P("floods", "monitoring_cycle", "Цикл мониторинга: паводки", "rakhimov", 60, 30),
    P("calibration", "industry_pilot", "Пилот: калибровка снимков", "karimov", 45, 20),
    # Работа, которая идёт по плану: строка «и ещё N по плану» без них потеряла бы масштаб.
    P("snow", "monitoring_cycle", "Цикл мониторинга: снежный покров", "rakhimov", 100, 5),
    P("forest", "monitoring_cycle", "Цикл мониторинга: лесные пожары", "tursunov", 110, 4),
    P("atlas", "platform", "Цифровой атлас земель", "tursunov", 130, 3),
    P("lab", "staff_education", "Учебная лаборатория ДЗЗ в вузе", "abdullaeva", 150, 7),
    P("uav", "service_order", "Заказ услуги: съёмка с БПЛА Каракалпакстана", "karimov", 80, 6),
    P("glossary", "standard", "Терминологический стандарт ДЗЗ", "yusupova", 140, 8),
    P("cadastre", "industry_pilot", "Пилот с кадастром: границы участков", "abdullaeva", 95, 9),
]

MILESTONES = [
    M("tz-constellation", "mission", "Согласование ТЗ на спутниковую группировку", 3, 2),
    M("tz-draft", "mission", "Разработка ТЗ", -5, 1),
    M("platform-acceptance", "portal", "Приёмка опытного образца платформы", -23, 1),
    M("standard-submit", "standard", "Внесение стандарта в агентство «Узстандарт»", 2, 1),
]

TASKS = [
    T(
        "drought-note",
        "drought",
        "Аналитическая справка по засухе для Кабинета министров",
        "rakhimov",
        -3,
        10,
        "analytical_note",
    ),
    T(
        "ijro-report",
        "drought",
        "Сведения по поручению ПФ-155 для Администрации Президента",
        "rakhimov",
        1,
        10,
        "ijro_report",
    ),
    T(
        "subplatform",
        "portal",
        "Выгрузка данных в субплатформу",
        "tursunov",
        -4,
        8,
        "subplatform_upload",
    ),
    T(
        "pilot-selection",
        "crops",
        "Отбор участников пилота с Минсельхозом",
        "abdullaeva",
        0,
        7,
        "participant_selection",
    ),
    T(
        "ecology-approval",
        "geodata",
        "Согласование проекта постановления с Минэкологии",
        "yusupova",
        20,
        5,
        "approval",
    ),
    T("mission-plan", "mission", "План работ по группировке на квартал", "karimov", 30, 3),
    T(
        "standard-review",
        "standard",
        "Рассмотрение замечаний к стандарту",
        "yusupova",
        25,
        4,
        "review_and_endorse",
    ),
    T(
        "khokimiyat-request",
        "floods",
        "Запрос сведений у хокимиятов о паводках",
        "rakhimov",
        30,
        15,
        "request_or_survey",
    ),
    T(
        "floods-summary",
        "floods",
        "Сводка по паводкам за сентябрь",
        "rakhimov",
        20,
        2,
        "analytical_note",
    ),
    T("jizzakh-visit", "calibration", "Выезд на полигон в Джизаке", "karimov", 10, 5, "site_visit"),
]


async def _codes(
    session: AsyncSession, model: type[ProjectTypeRef] | type[TaskTypeRef]
) -> dict[str, uuid.UUID]:
    """Код справочника → идентификатор. Сначала список: `dict(результат)` принимает результат
    SQLAlchemy за словарь — у него есть `keys()` — и падает."""
    rows = await session.execute(select(model.code, model.id))
    return dict(rows.tuples().all())


def _moment(day: date, zone: ZoneInfo, hours: int = 18) -> datetime:
    """Срок задачи — конец рабочего дня по Ташкенту, хранится в UTC (инвариант 8)."""
    return datetime.combine(day, time(hours), zone).astimezone(UTC)


async def _seed_base(session: AsyncSession, *, now: datetime, zone: ZoneInfo) -> dict[str, int]:
    today = local_date(now, zone)

    def ago(days: int) -> datetime:
        return now - timedelta(days=days)

    def on(days: int) -> date:
        return today + timedelta(days=days)

    types = await _codes(session, ProjectTypeRef)
    task_types = await _codes(session, TaskTypeRef)

    people = {key: Person(full_name=name, created_at=ago(90)) for key, name in PEOPLE.items()}
    session.add_all(people.values())
    partner = Organization(name=PARTNER, kind=OrganizationKind.MINISTRY.value, created_at=ago(90))
    session.add(partner)
    await session.flush()

    year = today.year
    projects: dict[str, Project] = {}
    for number, spec in enumerate(PROJECTS, start=1):
        projects[spec.key] = Project(
            code=f"PRJ-{year}-{number:03d}",
            title=spec.title,
            project_type_id=types[spec.type],
            started_on=on(-180),
            due_on=on(spec.due),
            original_due_on=on(spec.original if spec.original is not None else spec.due),
            status_code=ProjectStatus.IN_PROGRESS.value,
            responsible_person_id=people[spec.who].id,
            created_at=ago(spec.created),
        )
    session.add_all(projects.values())
    await session.flush()

    # Головное ведомство чужое: без движения с его стороны строка встаёт на ступень
    # «зависит от чужих», а не «молчит». У станции оно тоже чужое, но перенос её срока —
    # движение, и она идёт по плану: одно правило, два разных исхода.
    session.add_all(
        ProjectOrganization(
            project_id=projects[key].id,
            organization_id=partner.id,
            role=OrganizationRole.LEAD_AGENCY.value,
        )
        for key in ("station", "air")
    )

    milestones: dict[str, Milestone] = {}
    for mark in MILESTONES:
        milestones[mark.key] = Milestone(
            project_id=projects[mark.project].id,
            title=mark.title,
            due_on=on(mark.due),
            original_due_on=on(mark.due),
            sort_order=mark.order,
            created_at=ago(60),
        )
    session.add_all(milestones.values())

    tasks: dict[str, Task] = {}
    for number, work in enumerate(TASKS, start=1):
        due = _moment(on(work.due), zone)
        tasks[work.key] = Task(
            code=f"TSK-{year}-{number:04d}",
            title=work.title,
            task_type_id=task_types.get(work.kind),
            project_id=projects[work.project].id if work.project else None,
            assignee_person_id=people[work.who].id,
            status=TaskStatus.IN_PROGRESS.value,
            due_at=due,
            original_due_at=due,
            created_at=ago(work.created),
        )
    session.add_all(tasks.values())
    await session.flush()

    leader = await session.scalar(select(User).where(User.role == "leader"))
    decided_by = leader.id if leader else None

    session.add_all(
        [
            LeaderQuestion(
                target_type="milestone",
                target_id=milestones["tz-constellation"].id,
                text="Утвердить перенос вехи на две недели: поставщик задерживает документацию?",
                created_at=ago(6),
            ),
            LeaderQuestion(
                target_type="project",
                target_id=projects["geodata"].id,
                text="Вносить проект постановления в Кабинет министров в текущей редакции?",
                created_at=ago(2),
            ),
            # Решение, исполнение которого сорвано: срок вчера.
            LeaderDecision(
                target_type="task",
                target_id=tasks["jizzakh-visit"].id,
                kind=DecisionKind.HURRY.value,
                text="Поторопить: выезд на полигон в Джизаке",
                assignee_person_id=people["karimov"].id,
                due_on=on(-1),
                state=DecisionState.OPEN.value,
                decided_by=decided_by,
                created_at=ago(3),
            ),
            # Прошлое решение по вехе: строка покажет «поторопили», чтобы не торопить дважды.
            LeaderDecision(
                target_type="milestone",
                target_id=milestones["platform-acceptance"].id,
                kind=DecisionKind.HURRY.value,
                assignee_person_id=people["tursunov"].id,
                state=DecisionState.DONE.value,
                done_on=on(-2),
                decided_by=decided_by,
                created_at=ago(4),
            ),
            LeaderDecision(
                target_type="project",
                target_id=projects["geodata"].id,
                kind=DecisionKind.ESCALATE.value,
                text="Эскалировать: письмо в Минэкологии",
                assignee_person_id=people["yusupova"].id,
                state=DecisionState.OPEN.value,
                decided_by=decided_by,
                created_at=ago(5),
            ),
        ]
    )

    # Всё, что заведено выше, было «до прошлого визита».
    await session.execute(update(User).values(last_visit_at=datetime.now(UTC)))
    await session.flush()
    return {"projects": len(projects), "milestones": len(milestones), "tasks": len(tasks)}


async def _project(session: AsyncSession, title: str) -> Project:
    found = await session.scalar(select(Project).where(Project.title == title))
    assert found is not None, title
    return found


async def _milestone(session: AsyncSession, title: str) -> Milestone:
    found = await session.scalar(select(Milestone).where(Milestone.title == title))
    assert found is not None, title
    return found


async def _task(session: AsyncSession, title: str) -> Task:
    found = await session.scalar(select(Task).where(Task.title == title))
    assert found is not None, title
    return found


async def _after_visit(session: AsyncSession, *, now: datetime, zone: ZoneInfo) -> None:
    """То, что случилось после прошлого визита: это и увидит «С прошлого визита»."""
    today = local_date(now, zone)

    def on(days: int) -> date:
        return today + timedelta(days=days)

    acceptance = await _milestone(session, "Приёмка опытного образца платформы")
    acceptance.due_on = on(-16)
    await session.flush()
    acceptance.due_on = on(-9)

    station = await _project(session, "Приём наземной станции по соглашению о сотрудничестве")
    station.due_on = on(75)

    upload = await _task(session, "Выгрузка данных в субплатформу")
    upload.due_at = _moment(on(5), zone)

    draft = await _milestone(session, "Разработка ТЗ")
    draft.is_passed = True
    draft.passed_on = today

    report = await _task(session, "Сведения по поручению ПФ-155 для Администрации Президента")
    report.status = TaskStatus.DONE.value
    report.completed_at = now

    escalation = await session.scalar(
        select(LeaderDecision).where(LeaderDecision.kind == DecisionKind.ESCALATE.value)
    )
    if escalation:
        escalation.state = DecisionState.DONE.value
        escalation.done_on = today

    responsible = await session.scalar(
        select(Person).where(Person.full_name == PEOPLE["abdullaeva"])
    )
    types = await _codes(session, ProjectTypeRef)
    count = await session.scalar(select(func.count()).select_from(Project)) or 0
    session.add(
        Project(
            code=f"PRJ-{today.year}-{count + 1:03d}",
            title="Пилот с Минздравом: мониторинг вспышек",
            project_type_id=types["industry_pilot"],
            started_on=today,
            due_on=on(120),
            original_due_on=on(120),
            status_code=ProjectStatus.IN_PROGRESS.value,
            responsible_person_id=responsible.id if responsible else None,
        )
    )
    await session.flush()


async def _run() -> int:
    settings = get_settings()
    if settings.env == "production":
        print("вымышленные данные в рабочий контур не загружаются (инвариант 11)")
        return 1

    zone = ZoneInfo(settings.timezone)
    init_database(settings)
    try:
        async for session in session_scope():
            if await session.scalar(select(func.count()).select_from(Project)):
                print("проекты в базе уже есть — вымышленные данные не добавляются")
                return 0
            added = await _seed_base(session, now=datetime.now(UTC), zone=zone)

        async for session in session_scope():
            await _after_visit(session, now=datetime.now(UTC), zone=zone)
    finally:
        await dispose_database()

    logger.info("demo_loaded", **added)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
