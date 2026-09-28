"""Вымышленные данные в базе дают то, что заказчик утвердил на экранах Пульта, «Проектов»,
«Задач», «Программ», «Календаря» и «Захвата».

Экран утверждали по вымышленному серверу во фронтенде, а превью показывает сервер. Если
демо в базе разойдётся с утверждённым, заказчик увидит на превью не тот экран, что
принимал, — и не поймёт, изменилось ли правило или только данные. Поэтому проверяется не
«что записано», а что из записанного насчитал сервер: ступени — сервисом показателей,
переносы — по журналу изменений.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import demo
from app.domain.attention import Attention
from app.domain.audit import AuditAction
from app.domain.clock import local_date, now_utc
from app.domain.cycles import occurrences
from app.domain.dictionaries import OrganizationRole, ProjectStatus, TaskStatus
from app.domain.pult import MILESTONES, PROJECTS, AuditEntry, due_shift
from app.repos import attention as snapshot
from app.repos.models import (
    AuditLog,
    LeaderQuestion,
    Milestone,
    Organization,
    Project,
    ProjectOrganization,
    Task,
    TaskChecklistItem,
)
from app.services import calendar, captures, metrics, programs
from app.services import tasks as task_service

pytestmark = pytest.mark.infra

TASHKENT = ZoneInfo("Asia/Tashkent")

SPECS = {spec.key: spec for spec in demo.PROJECTS}

STEPS = {
    "geodata": (Attention.AWAITING_DECISION, 2),
    "interns": (Attention.BURNING, 6),
    "air": (Attention.BLOCKED_BY_OTHERS, 25),
    "aerial": (Attention.SILENT, 21),
    "lab": (Attention.SILENT, 30),
    "infrastructure": (Attention.SILENT, 16),
    "insurance": (Attention.SILENT, 20),
}
"""Ступени проектов на утверждённых экранах; остальные незавершённые идут по плану."""

MILESTONE_STEPS = [
    ("Согласование ТЗ на спутниковую группировку", Attention.AWAITING_DECISION, 6),
    ("Приёмка опытного образца платформы", Attention.OVERDUE, 9),
    ("Внесение стандарта в агентство «Узстандарт»", Attention.BURNING, 2),
    ("Итоги и отчёт", Attention.BURNING, 6),
    ("Получение космических снимков", Attention.BURNING, 0),
    ("Площадка станции приёма в Самарканде", Attention.OVERDUE, 8),
    ("Смета конгресса на следующий год внесена в Кабмин", Attention.AWAITING_DECISION, 1),
]
"""Вехи в лестнице: три из сценария Пульта, две — из шаблонов (стажировки, паводки), две —
с экрана «Программы»."""

PROGRAMS = {
    "mission": {"calibration", "insurance"},
    "iac": {"venue", "science", "volunteers"},
    "infrastructure": {"portal", "station"},
    "staff": {"interns", "lab"},
    "catalogue": set(),
    "strategy": set(),
    "digital": set(),
}
"""Программы экрана «Программы» и их подпроекты."""

CABINET = "Внесение проекта постановления в Кабинет министров"

TASK_STEPS = [
    (CABINET, Attention.AWAITING_DECISION, 2),
    ("Аналитическая справка по засухе для Кабинета министров", Attention.OVERDUE, 3),
    ("Сведения по поручению ПФ-155 §5.1", Attention.OVERDUE, 1),
    ("Позвонить в Минфин по смете миссии на следующий год", Attention.BURNING, 0),
    ("Отбор участников пилота с Минсельхозом", Attention.BURNING, 0),
    ("Сведения для Администрации Президента по мониторингу водохранилищ", Attention.BURNING, 1),
    ("Согласование проекта постановления с Минэкологии", Attention.BURNING, 3),
    ("Выезд на полигон в Джизаке", Attention.BURNING, 4),
    ("Запрос сведений у хокимиятов о паводках", Attention.BURNING, 5),
    ("Выгрузка данных в субплатформу", Attention.BURNING, 5),
    ("Подобрать помещение для учебной лаборатории", Attention.SILENT, 30),
    ("Список оборудования лаборатории", Attention.SILENT, 30),
    ("Проект соглашения с Минэкологии", Attention.SILENT, 25),
    ("Договор с исполнителем аэрофотосъёмки", Attention.SILENT, 21),
    ("Согласование полётного задания", Attention.SILENT, 21),
]
"""Задачи в лестнице Пульта — сроки экрана «Задачи» и тишина молчащих проектов.

Выгрузка в субплатформу горит, а не просрочена, как на экране «Задачи»: её перенос после
визита — событие Пульта, и он прав (`app.demo`, модуль). Остальные открытые задачи — по
плану.
"""

WITHOUT_PROJECT = {
    "Позвонить в Минфин по смете миссии на следующий год",
    "Тезисы к совещанию по космическому мониторингу",
    "Сведения для Администрации Президента по мониторингу водохранилищ",
    "Сведения по поручению ПФ-155 §5.1",
}

CHECKLISTS = {
    "Аналитическая справка по засухе для Кабинета министров": (2, 3),
    "Сведения по поручению ПФ-155 §5.1": (0, 2),
    "Согласование проекта постановления с Минэкологии": (3, 4),
    "Выезд на полигон в Джизаке": (1, 3),
    "ТЗ на модуль каталога снимков": (1, 5),
}
"""Чек-листы экрана «Задачи»: название → (отмечено, всего)."""

STATUSES = {
    TaskStatus.NEW: {
        "План работ по группировке на квартал",
        "Позвонить в Минфин по смете миссии на следующий год",
        "Тезисы к совещанию по космическому мониторингу",
        "Опросник для хокимиятов по снежному покрову",
    },
    TaskStatus.IN_REVIEW: {"Согласование проекта постановления с Минэкологии"},
    TaskStatus.CANCELLED: {"Выгрузка в прежний портал"},
}
"""Статусы, которые экран «Задачи» задал явно; безымянные задачи — в работе или готовы."""


class Loaded:
    """Демо после обеих транзакций и проекты по ключам экрана."""

    def __init__(self, now: datetime, projects: dict[str, Project]) -> None:
        self.now = now
        self.today = local_date(now, TASHKENT)
        self.projects = projects

    def on(self, days: int) -> date:
        return self.today + timedelta(days=days)

    def key_of(self, entity_id: uuid.UUID) -> str | None:
        return next((key for key, each in self.projects.items() if each.id == entity_id), None)


@pytest.fixture
async def loaded(session: AsyncSession) -> Loaded:
    now = now_utc()
    await demo.before_visit(session, now=now, zone=TASHKENT)
    await demo.after_visit(session, now=now, zone=TASHKENT)
    today = local_date(now, TASHKENT)
    keys = {demo.title_of(spec, today): spec.key for spec in demo.PROJECTS}
    keys |= {demo.NEW_PROJECT: "new"}
    projects = {keys[each.title]: each for each in await session.scalars(select(Project))}
    return Loaded(now, projects)


class TestProjects:
    async def test_the_approved_projects_and_the_one_created_after_the_visit(
        self, session: AsyncSession, loaded: Loaded
    ) -> None:
        total = len(demo.PROJECTS) + 1
        assert await session.scalar(select(func.count()).select_from(Project)) == total
        year = loaded.today.year
        for number, spec in enumerate(demo.PROJECTS, start=1):
            project = loaded.projects[spec.key]
            assert project.code == f"PRJ-{year}-{number:03d}"
            assert project.started_on == loaded.on(spec.start)
            assert project.due_on == loaded.on(spec.due)
            # Направление и регион экран называл словами; все, что есть в справочниках,
            # обязаны найтись — иначе срез по ним на превью окажется пустым.
            assert (project.direction_id is not None) is (spec.direction is not None), spec.key
            assert (project.region_id is not None) is (spec.region is not None), spec.key
        assert loaded.projects["new"].code == f"PRJ-{year}-{total:03d}"

    async def test_paused_finished_and_cancelled_keep_their_reasons(self, loaded: Loaded) -> None:
        expected = {
            "snow": (ProjectStatus.ON_HOLD, SPECS["snow"].reason),
            "lab": (ProjectStatus.ON_HOLD, SPECS["lab"].reason),
            "glossary": (ProjectStatus.DONE, None),
            "hydro": (ProjectStatus.DONE, None),
            "legacy": (ProjectStatus.CANCELLED, SPECS["legacy"].reason),
        }
        for key, (status, reason) in expected.items():
            project = loaded.projects[key]
            assert (project.status_code, project.status_reason) == (status.value, reason), key
            if status.requires_reason:
                assert reason

    async def test_programmes_and_their_subprojects(self, loaded: Loaded) -> None:
        programs = {key for key, each in loaded.projects.items() if each.is_multiyear}
        assert programs == set(PROGRAMS)
        for key, children in PROGRAMS.items():
            parent = loaded.projects[key].id
            found = {
                child for child, each in loaded.projects.items() if each.parent_project_id == parent
            }
            assert found == children, key

    async def test_yearly_reports_are_named_by_year(
        self, session: AsyncSession, loaded: Loaded
    ) -> None:
        titles = set(
            await session.scalars(
                select(Milestone.title).where(
                    Milestone.project_id == loaded.projects["strategy"].id,
                    Milestone.title.like("Отчёт об исполнении за %"),
                )
            )
        )
        # Сроки — 15 февраля пяти лет подряд, начиная с текущего: отчёт за прошлый год и
        # четыре следующих, в какой бы день ни загрузили демо.
        first = loaded.today.year - 1
        assert titles == {f"Отчёт об исполнении за {first + shift} год" for shift in range(5)}

    async def test_programme_titles_follow_their_dates(self, loaded: Loaded) -> None:
        for key in ("infrastructure", "staff", "catalogue", "digital"):
            project = loaded.projects[key]
            years = f"{project.started_on.year}–{project.due_on.year}"
            assert project.title.endswith(years), project.title
        assert loaded.projects["iac"].title.startswith(f"IAC-{loaded.projects['iac'].due_on.year}")
        strategy = loaded.projects["strategy"]
        assert f"до {strategy.due_on.year} года" in strategy.title

    async def test_programmes_answer_as_on_the_screen(
        self, session: AsyncSession, loaded: Loaded
    ) -> None:
        """«Успеваем?» — все три ответа, как на экране: не успевает, успевает, мало данных."""
        view = await programs.load(
            session, now=loaded.now, zone=TASHKENT, locale="ru", is_demo=True
        )
        by_key = {loaded.key_of(item.id): item for item in view.items}
        verdicts = {
            key: item.pace.verdict.value if item.pace else None for key, item in by_key.items()
        }
        assert verdicts == {
            "catalogue": "behind",
            "iac": "on_track",
            "infrastructure": "on_track",
            "staff": "on_track",
            "mission": "little_data",
            "strategy": "little_data",
            "digital": None,
        }
        # Запас над порогом «мало данных»: ответ не пропадает через неделю после загрузки.
        for key in ("catalogue", "iac", "infrastructure", "staff"):
            pace = by_key[key].pace
            assert pace is not None
            assert pace.closed_tasks >= pace.min_closed_tasks + 2, key
        assert by_key["infrastructure"].original_due_on != by_key["infrastructure"].due_on

    async def test_center_roles_and_outside_lead(
        self, session: AsyncSession, loaded: Loaded
    ) -> None:
        rows = await session.execute(
            select(
                ProjectOrganization.project_id,
                ProjectOrganization.role,
                Organization.is_founded_by_agency,
            ).join(Organization, Organization.id == ProjectOrganization.organization_id)
        )
        center = set()
        outside = set()
        for project_id, role, is_center in rows:
            key = loaded.key_of(project_id)
            if is_center:
                center.add((key, role))
            elif role == OrganizationRole.LEAD_AGENCY.value:
                outside.add(key)

        assert center == {
            (spec.key, spec.center.value) for spec in demo.PROJECTS if spec.center is not None
        }
        assert outside == {"station", "air"}

    async def test_tasks_add_up_to_the_screen(self, session: AsyncSession, loaded: Loaded) -> None:
        """Задачи экрана «Задачи» заняли места безымянных, и готовность не сдвинулась.

        Отменённая в «сделано N из M» не входит — так считает read-модель «Проектов»
        (`app.repos.projects`). Демо заводит отменённую выгрузку прежнего портала, и проверка
        считает по тому же правилу: иначе «0 из 2» у отменённого проекта стало бы здесь
        «0 из 3», хотя на экране осталось прежним.
        """
        rows = await session.execute(
            select(Task.project_id, Task.status, func.count()).group_by(
                Task.project_id, Task.status
            )
        )
        done: Counter[str | None] = Counter()
        total: Counter[str | None] = Counter()
        for project_id, status, count in rows:
            key = loaded.key_of(project_id)
            if status != TaskStatus.CANCELLED.value:
                total[key] += count
            if status == TaskStatus.DONE.value:
                done[key] += count

        for spec in demo.PROJECTS:
            assert (done[spec.key], total[spec.key]) == spec.tasks, spec.key


async def later_shifts(
    session: AsyncSession, entity_type: str
) -> dict[uuid.UUID, list[tuple[date, date]]]:
    """Переносы позже по журналу — тем же правилом, что «Держим ли мы свои сроки?»."""
    rows = await session.execute(
        select(
            AuditLog.occurred_at,
            AuditLog.entity_type,
            AuditLog.entity_id,
            AuditLog.action,
            AuditLog.changes,
        ).where(
            AuditLog.entity_type == entity_type,
            AuditLog.action == AuditAction.UPDATED.value,
        )
    )
    shifts: dict[uuid.UUID, list[tuple[date, date]]] = {}
    for occurred_at, kind, entity_id, action, changes in rows:
        moved = due_shift(AuditEntry(occurred_at, kind, entity_id, action, changes), TASHKENT)
        if moved and moved[1] > moved[0]:
            shifts.setdefault(entity_id, []).append(moved)
    # Записи одной транзакции помечены одним моментом: порядок между ними не хранится,
    # сравнивается набор переносов.
    return {entity_id: sorted(moves) for entity_id, moves in shifts.items()}


class TestMoves:
    async def test_portal_and_station_moved_later_once(
        self, session: AsyncSession, loaded: Loaded
    ) -> None:
        shifts = {
            loaded.key_of(entity_id): moves
            for entity_id, moves in (await later_shifts(session, PROJECTS)).items()
        }
        assert shifts == {
            "portal": [(loaded.on(30), loaded.on(60))],
            "station": [(loaded.on(61), loaded.on(75))],
        }
        for key in ("portal", "station"):
            project = loaded.projects[key]
            spec = SPECS[key]
            assert spec.original is not None
            assert project.original_due_on == loaded.on(spec.original)
            assert project.due_on == loaded.on(spec.due)

    async def test_acceptance_moved_later_twice(
        self, session: AsyncSession, loaded: Loaded
    ) -> None:
        """Веха, которую продлевают хронически, — строка Пульта: с −23 через −16 к −9."""
        acceptance = await session.scalar(
            select(Milestone).where(
                Milestone.project_id == loaded.projects["portal"].id,
                Milestone.title == "Приёмка опытного образца платформы",
            )
        )
        assert acceptance is not None
        assert (acceptance.original_due_on, acceptance.due_on) == (loaded.on(-23), loaded.on(-9))
        shifts = await later_shifts(session, MILESTONES)
        assert shifts == {
            acceptance.id: [(loaded.on(-23), loaded.on(-16)), (loaded.on(-16), loaded.on(-9))]
        }


class TestLadder:
    async def test_projects_stand_on_the_approved_steps(
        self, session: AsyncSession, loaded: Loaded
    ) -> None:
        ladder = await metrics.ladder(session, today=loaded.today, zone=TASHKENT)
        steps = {
            loaded.key_of(row.entity_id): (row.attention, row.deviation)
            for row in ladder.rows
            if row.section == "projects"
        }
        assert steps == STEPS

    async def test_finished_and_cancelled_are_not_in_the_ladder(
        self, session: AsyncSession, loaded: Loaded
    ) -> None:
        items = await snapshot.load_items(session, zone=TASHKENT)
        in_snapshot = {loaded.key_of(item.entity_id) for item in items}
        assert {"glossary", "hydro", "legacy"}.isdisjoint(in_snapshot)
        # Пауза — не конец работы: снег в снимке есть и идёт по плану.
        assert "snow" in in_snapshot

    async def test_milestones_on_the_ladder(self, session: AsyncSession, loaded: Loaded) -> None:
        ladder = await metrics.ladder(session, today=loaded.today, zone=TASHKENT)
        marks = sorted(
            (row.title or "", row.attention, row.deviation)
            for row in ladder.rows
            if row.section == "milestones"
        )
        assert marks == sorted(MILESTONE_STEPS)

    async def test_tasks_on_the_ladder(self, session: AsyncSession, loaded: Loaded) -> None:
        ladder = await metrics.ladder(session, today=loaded.today, zone=TASHKENT)
        rows = sorted(
            (row.title or "", row.attention, row.deviation)
            for row in ladder.rows
            if row.section == "tasks"
        )
        assert rows == sorted(TASK_STEPS)

    async def test_a_question_on_a_task_awaits_the_leader(
        self, session: AsyncSession, loaded: Loaded
    ) -> None:
        """Вопрос по задаче ставит её на «ждёт решения» — выше её собственного срока."""
        task = await session.scalar(select(Task).where(Task.title == CABINET))
        assert task is not None
        question = await session.scalar(
            select(LeaderQuestion).where(
                LeaderQuestion.target_type == "task", LeaderQuestion.target_id == task.id
            )
        )
        assert question is not None
        assert question.closed_at is None
        assert question.text == "Вносить в текущей редакции или дождаться замечаний Минюста?"

        ladder = await metrics.ladder(session, today=loaded.today, zone=TASHKENT)
        row = next(row for row in ladder.rows if row.entity_id == task.id)
        assert (row.section, row.attention, row.deviation) == (
            "tasks",
            Attention.AWAITING_DECISION,
            2,
        )


class TestTasks:
    async def test_tasks_without_a_project(self, session: AsyncSession, loaded: Loaded) -> None:
        loose = list(await session.scalars(select(Task).where(Task.project_id.is_(None))))
        assert {task.title for task in loose} == WITHOUT_PROJECT
        # Метки Ижро экрана не заводятся: поручения приходят привозом в блоке 2 (`app.demo`).
        assert all(task.ijro_assignment_id is None for task in loose)

    async def test_every_status_with_the_stamps_the_service_would_set(
        self, session: AsyncSession, loaded: Loaded
    ) -> None:
        tasks = list(await session.scalars(select(Task)))
        assert {task.status for task in tasks} == {status.value for status in TaskStatus}
        for status, titles in STATUSES.items():
            assert {task.title for task in tasks if task.status == status.value} == titles
        for task in tasks:
            status = TaskStatus(task.status)
            assert (task.started_at is None) is (status is TaskStatus.NEW), task.title
            assert (task.completed_at is not None) is status.is_terminal, task.title

    async def test_closed_on_the_screen_days(self, session: AsyncSession, loaded: Loaded) -> None:
        """Закрытые с экрана «Задачи»: ТЗ — сегодня, выгрузка — месяц назад, отчёт — сегодня.

        Отчёт по ПФ-155 экран закрывал вчера и без проекта, а база — сегодня после визита:
        это событие Пульта (`app.demo`, модуль).
        """
        closed = {
            task.title: local_date(task.completed_at, TASHKENT)
            for task in await session.scalars(
                select(Task).where(
                    Task.title.in_(
                        [
                            "Разработка ТЗ спутниковой группировки",
                            "Выгрузка в прежний портал",
                            "Сведения по поручению ПФ-155 для Администрации Президента",
                        ]
                    )
                )
            )
            if task.completed_at is not None
        }
        assert closed == {
            "Разработка ТЗ спутниковой группировки": loaded.today,
            "Выгрузка в прежний портал": loaded.on(-30),
            "Сведения по поручению ПФ-155 для Администрации Президента": loaded.today,
        }

    async def test_checklists_as_on_the_screen(self, session: AsyncSession, loaded: Loaded) -> None:
        rows = await session.execute(
            select(
                Task.title,
                func.count().filter(TaskChecklistItem.is_done.is_(True)),
                func.count(),
            )
            .join(TaskChecklistItem, TaskChecklistItem.task_id == Task.id)
            .group_by(Task.title)
        )
        assert {title: (done, total) for title, done, total in rows} == CHECKLISTS


class TestCalendar:
    @pytest.mark.parametrize(
        "today", [date(2026, 9, 28), date(2026, 11, 14), date(2026, 11, 15), date(2026, 12, 31)]
    )
    def test_cycle_without_dates_stays_so_on_any_load_day(self, today: date) -> None:
        # С 15 ноября горизонт доходит до 15 ноября следующего года: год начала «от прошлого»
        # дал бы дату в горизонте.
        spec = next(each for each in demo.CYCLES if each.after_horizon)
        anchor = demo._anchor(spec, today)
        dates = occurrences(
            rule=spec.rule,
            month=spec.month,
            day=spec.day,
            every_years=spec.every_years,
            anchor_year=anchor,
            since=today,
        )
        assert dates == []
        assert date(anchor, spec.month, spec.day) > today

    async def test_the_cycles_of_the_approved_screen(
        self, session: AsyncSession, loaded: Loaded
    ) -> None:
        cycles = await calendar.cycles(session, today=loaded.today)
        assert {cycle.title for cycle in cycles} == {spec.title for spec in demo.CYCLES}
        # Переаттестация — год начала за горизонтом: за год вперёд дат нет, видна в списке.
        operators = next(cycle for cycle in cycles if cycle.title.startswith("Переаттестация"))
        assert operators.dates == [] and operators.next_date is not None
        assert operators.owner is not None and operators.owner.id == loaded.projects["station"].id

    async def test_hot_days_and_overdue_as_on_the_approved_screen(
        self, session: AsyncSession, loaded: Loaded
    ) -> None:
        view = await calendar.load(
            session,
            since=loaded.today,
            until=loaded.on(13),
            now=loaded.now,
            zone=TASHKENT,
            is_demo=True,
        )
        # Сегодня, через 10 и через 20 дней — дни сроков базы; даты циклов по календарю в
        # другой день загрузки могут добавить горячий день, но не убрать эти.
        hot = [day.date for day in view.hot_ahead]
        assert {loaded.today, loaded.on(10), loaded.on(20)} <= set(hot)
        assert len(view.overdue) == 5
        # Через 6 дней итоговая веха стажировок в день срока проекта — одна строка.
        interns = [
            item
            for item in view.items
            if item.date == loaded.on(6)
            and item.owner is not None
            and item.owner.id == loaded.projects["interns"].id
        ]
        assert [(item.kind.value, item.ends_project) for item in interns] == [("milestone", True)]


class TestCaptures:
    async def test_the_captures_of_the_approved_screen(
        self, session: AsyncSession, loaded: Loaded
    ) -> None:
        view = await captures.load(session, now=loaded.now, zone=TASHKENT, is_demo=True)
        kinds = [each.kind.value for each in view.recent]
        assert sorted(kinds) == sorted(spec.kind.value for spec in demo.CAPTURES)
        # Сначала новые: письмо два часа назад, просьба — когда заведена справка по засухе.
        assert kinds[0] == "letter" and kinds[-1] == "request"
        letter = view.recent[0]
        assert (letter.author.value, letter.due_on, letter.destination) == (
            "assistant",
            loaded.on(12),
            "inbox",
        )

    async def test_the_request_is_the_drought_note_and_marked_in_tasks(
        self, session: AsyncSession, loaded: Loaded
    ) -> None:
        view = await captures.load(session, now=loaded.now, zone=TASHKENT, is_demo=True)
        request = next(each for each in view.recent if each.kind.value == "request")
        assert request.text == "Аналитическая справка по засухе для Кабинета министров"
        assert (request.author.value, request.destination) == ("leader", "tasks")
        assert request.due_on == loaded.on(-3)

        section = await task_service.load(
            session, now=loaded.now, zone=TASHKENT, locale="ru", is_demo=True
        )
        marked = [card.title for card in section.items if card.is_request]
        assert marked == ["Аналитическая справка по засухе для Кабинета министров"]
