"""Вымышленные данные для разработки и превью — тот же набор, что на утверждённых экранах.

    uv run python -m app.demo

Экраны Пульта и «Проектов» заказчик утвердил на вымышленных данных (25.09.2026). Здесь те
же люди, проекты, вехи и задачи, но в базе: API считает их тем же кодом, что будет считать
настоящие, и превью обязано показать то, что утверждали. Проекты повторяют вымышленный
сервер экрана (`frontend/src/sections/projects/demo.ts` в коммите 96f4ce2) — сроки, статусы,
вехи, роли Центра, «что мешает», вопросы; строки Пульта сверх того — задачи с их сроками,
решения руководителя и события «после визита». Критерий блока 0 «в демо — вымышленные
данные» (перенесён в блок 1) закрывается этим же.

**В рабочем контуре не запускается никогда** (инвариант 11): отказ по `ORBITA_ENV`, а не
по доброй воле того, кто запускает. Повторный запуск ничего не добавляет: если проекты
уже есть, команда останавливается.

Две транзакции, а не одна. Первая заводит всё, что было «до прошлого визита», и ставит
отметку визита обоим пользователям. Вторая делает то, что случилось «после»: переносит
сроки, проходит веху, закрывает задачу, заводит проект. Так «С прошлого визита» и «Держим
ли мы свои сроки?» читают настоящий журнал изменений, а не заготовленный список.

**Ступени считает сервер, а не этот файл.** Экран задавал «дней без движения» числом, а
сервер выводит его из моментов (`app.repos.attention`): самое свежее из правки проекта,
подтверждения «что мешает», движения его задач и вех. Поэтому моменты здесь расставлены
так, чтобы вывод совпал с числом экрана, — и расходятся с ним только там, где иначе нельзя:

- после визита геопортал, миссия и засуха оживают — перенос срока, пройденная веха и
  закрытая задача и есть движение. Ступени от этого не меняются: у всех трёх тишина была
  короче порога;
- у постановления о геоданных «что мешает» подтверждали три дня назад, а экран писал пять
  дней без движения. Подтверждение — тоже движение, сервер видит три;
- открытые задачи молчащих проектов (программа по воздуху, аэрофотосъёмка, лаборатория)
  молчат вместе с ними и встают на Пульт своими строками: тишина проекта — это и есть
  самая свежая из тишин его задач, развести их нельзя.

Люди выдуманы; организации — только в роли партнёра по вымышленному проекту и Центр из
справочников.
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
    Direction,
    LeaderDecision,
    LeaderQuestion,
    Milestone,
    Organization,
    Person,
    Project,
    ProjectOrganization,
    ProjectTypeMilestone,
    ProjectTypeRef,
    Region,
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

WORK_BY_TYPE: dict[str, tuple[str, ...]] = {
    "monitoring_cycle": (
        "Заявка на космические снимки",
        "Проверка облачности на снимках",
        "Сверка результатов с данными хокимиятов",
        "Карта изменений за период",
        "Справка по итогам цикла",
    ),
    "regulation": (
        "Сводная таблица замечаний министерств",
        "Пояснительная записка к проекту акта",
        "Заключение юридического отдела",
    ),
    "platform": (
        "Приёмка модуля каталога снимков",
        "Нагрузочное испытание",
        "Инструкция пользователя",
        "Перенос данных из прежнего портала",
        "Обучение операторов",
        "Акт опытной эксплуатации",
    ),
    "industry_pilot": (
        "Соглашение с отраслевым партнёром",
        "Выбор тестовых участков",
        "Отчёт о точности классификации",
    ),
    "standard": (
        "Сравнение с международными стандартами",
        "Рассылка проекта на отзыв",
        "Сводка отзывов",
    ),
    "staff_education": (
        "План стажировок на полугодие",
        "Отбор стажёров",
        "Программа занятий",
        "Письмо ректору о помещении",
        "Список оборудования лаборатории",
        "Итоговая аттестация стажёров",
    ),
    "international": (
        "Проект соглашения с Минэкологии",
        "Перевод технической документации",
        "Согласование графика визита",
    ),
    "service_order": (
        "Согласование полётного задания",
        "Договор с исполнителем съёмки",
        "Приёмка материалов съёмки",
    ),
    "satellite_mission": (
        "Сравнение предложений изготовителей",
        "Расчёт орбитальных параметров",
        "Смета миссии на следующий год",
    ),
    "higher_authority_order": (
        "Сведения по водохранилищам за квартал",
        "Справка для Администрации Президента",
    ),
}
"""Названия задач, которых экран не называл, — по типу проекта.

Экран задавал у проекта «сделано N из M» и называл одну-две задачи; остальные нужны,
чтобы готовность на сервере сошлась с утверждённой. Данные вымышленные целиком (инвариант
11), и безымянная «Рабочая задача 17» в карточке проекта или строкой на Пульте выглядела
бы поломкой, а не примером работы.
"""


@dataclass(frozen=True, slots=True)
class M:
    """Веха, которую экран задал явно. Сроки — в днях от сегодня."""

    title: str
    due: int
    original: int | None = None
    """Первый срок, если веху переносили. Веха заводится с ним, а переносит её
    `after_visit` — иначе в журнале не будет переносов, которые показывает Пульт."""

    passed_ago: int | None = None
    """Сколько дней назад пройдена; `None` — не пройдена."""


@dataclass(frozen=True, slots=True)
class P:
    """Проект экрана «Проекты». Поля и умолчания — как у `Spec` в `demo.ts`."""

    key: str
    type: str
    title: str
    who: str
    start: int
    due: int
    original: int | None = None
    """Первый срок. Задан — значит, срок перенесли один раз, и перенос случится после
    визита (`after_visit`): «Держим ли мы свои сроки?» читает его из журнала."""

    status: ProjectStatus = ProjectStatus.IN_PROGRESS
    reason: str | None = None
    parent: str | None = None
    multiyear: bool = False
    impediment: tuple[str, int] | None = None
    """Текст и сколько дней назад его подтверждали."""

    life: int = 3
    """Дней без движения к моменту загрузки — `lifeAgo` экрана."""

    lead_outside: bool = False
    center: OrganizationRole | None = None
    question: tuple[str, int] | None = None
    """Вопрос руководителю по проекту и сколько дней он ждёт."""

    marks: tuple[M, ...] = ()
    """Явные вехи; пусто — вехи из шаблона типа, как у заведённого настоящего проекта."""

    tasks: tuple[int, int] = (0, 2)
    """Сделано и всего задач — после визита, как на экране."""

    direction: str | None = None
    region: str | None = None


@dataclass(frozen=True, slots=True)
class T:
    """Задача со сроком и типом — из тех, что стоят строками на Пульте."""

    key: str
    project: str | None
    title: str
    who: str
    due: int
    created: int
    kind: str = "other"
    closed_after_visit: bool = False


@dataclass(frozen=True, slots=True)
class Step:
    """Веха шаблона типа, как она лежит в справочнике."""

    title: str
    offset: int
    order: int


PROJECTS = [
    P(
        "mission",
        "satellite_mission",
        "Спутниковая миссия «Навоий-2»",
        "karimov",
        start=-220,
        due=590,
        multiyear=True,
        life=1,
        center=OrganizationRole.CO_EXECUTOR,
        direction="Космический мониторинг",
        marks=(
            # Пройдена сегодня, после визита: заведённая пройденной, она не дала бы строки
            # «веха пройдена» в «С прошлого визита».
            M("Разработка ТЗ", -5),
            M("Согласование ТЗ на спутниковую группировку", 3),
            M("Договор с изготовителем", 120),
            M("Запуск", 500),
        ),
        tasks=(3, 6),
    ),
    P(
        "geodata",
        "regulation",
        "Постановление о порядке обмена геоданными",
        "yusupova",
        start=-80,
        due=40,
        life=5,
        question=("Вносить проект постановления в Кабинет министров в текущей редакции?", 2),
        impediment=("Ждём заключение Минюста по разделу о персональных данных", 3),
        # На экране направление — «Нормативная база», а в справочнике такого нет. Демо не
        # заводит записей справочника: их правит помощник, и выдуманная осталась бы в нём.
        direction=None,
        tasks=(2, 4),
    ),
    P(
        "drought",
        "monitoring_cycle",
        "Цикл мониторинга: засуха-2026",
        "rakhimov",
        start=-70,
        due=20,
        life=10,
        center=OrganizationRole.EXECUTOR,
        region="Джизакская область",
        tasks=(1, 3),
    ),
    P(
        "portal",
        "platform",
        "Геопортал агентства",
        "tursunov",
        start=-150,
        due=60,
        original=30,
        life=8,
        impediment=("Поставщик не передал исходный код модуля карт", 21),
        marks=(
            M("Техническое задание", -120, passed_ago=118),
            M("Приёмка опытного образца платформы", -9, original=-23),
            M("Опытная эксплуатация", 20),
            M("Ввод в эксплуатацию", 60),
        ),
        tasks=(4, 7),
    ),
    P(
        "crops",
        "industry_pilot",
        "Пилот: мониторинг посевов",
        "abdullaeva",
        start=-40,
        due=110,
        life=7,
        center=OrganizationRole.CO_EXECUTOR,
        tasks=(1, 3),
    ),
    P(
        "standard",
        "standard",
        "Стандарт на снимки ДЗЗ",
        "yusupova",
        start=-118,
        due=62,
        life=4,
        marks=(
            M("Разработка проекта стандарта", -58, passed_ago=55),
            M("Внесение стандарта в агентство «Узстандарт»", 2),
            M("Утверждение и регистрация", 62),
        ),
        tasks=(2, 3),
    ),
    P(
        "interns",
        "staff_education",
        "Кадры: стажировки в Центре мониторинга",
        "abdullaeva",
        start=-144,
        due=6,
        life=6,
        center=OrganizationRole.EXECUTOR,
        tasks=(5, 6),
    ),
    P(
        "station",
        "international",
        "Приём наземной станции по соглашению о сотрудничестве",
        "rakhimov",
        start=-75,
        due=75,
        original=61,
        life=0,
        lead_outside=True,
        tasks=(0, 2),
    ),
    # Головное ведомство чужое, и с его стороны три недели тишины — «зависит от чужих».
    # Станция для этого не годится: перенос её срока — тоже движение, и она оживает.
    P(
        "air",
        "international",
        "Совместная программа наблюдения за качеством воздуха",
        "yusupova",
        start=-50,
        due=100,
        life=25,
        lead_outside=True,
        impediment=("Министерство экологии не прислало свой проект соглашения", 25),
        tasks=(0, 1),
    ),
    P(
        "aerial",
        "service_order",
        "Заказ услуги: аэрофотосъёмка Ферганской долины",
        "tursunov",
        start=-21,
        due=69,
        life=21,
        region="Ферганская область",
        tasks=(0, 2),
    ),
    P(
        "floods",
        "monitoring_cycle",
        "Цикл мониторинга: паводки",
        "rakhimov",
        start=-30,
        due=60,
        life=2,
        center=OrganizationRole.EXECUTOR,
        tasks=(1, 3),
    ),
    P(
        "calibration",
        "industry_pilot",
        "Пилот: калибровка снимков",
        "karimov",
        start=-20,
        due=130,
        parent="mission",
        life=5,
        tasks=(0, 2),
    ),
    # Работа, которая идёт по плану: строка «и ещё N по плану» без них потеряла бы масштаб.
    P(
        "forest",
        "monitoring_cycle",
        "Цикл мониторинга: лесные пожары",
        "tursunov",
        start=-4,
        due=86,
        life=4,
        center=OrganizationRole.CO_EXECUTOR,
        tasks=(0, 2),
    ),
    P(
        "atlas",
        "platform",
        "Цифровой атлас земель",
        "tursunov",
        start=-40,
        due=140,
        life=3,
        center=OrganizationRole.EXECUTOR,
        tasks=(2, 5),
    ),
    P(
        "uav",
        "service_order",
        "Заказ услуги: съёмка с БПЛА Каракалпакстана",
        "karimov",
        start=-6,
        due=84,
        life=6,
        center=OrganizationRole.EXECUTOR,
        region="Республика Каракалпакстан",
        tasks=(0, 1),
    ),
    P(
        "cadastre",
        "industry_pilot",
        "Пилот с кадастром: границы участков",
        "abdullaeva",
        start=-9,
        due=141,
        life=9,
        tasks=(0, 2),
    ),
    # Пауза не снимает проект с лестницы — терминальны только завершённый и отменённый
    # (`ProjectStatus.is_terminal`). Лаборатория месяц без движения и молчит, снег — двенадцать
    # дней, в пределах порога, и идёт по плану: забытая пауза видна, свежая — нет.
    P(
        "snow",
        "monitoring_cycle",
        "Цикл мониторинга: снежный покров",
        "rakhimov",
        start=-40,
        due=50,
        status=ProjectStatus.ON_HOLD,
        reason="Сезон съёмки начинается в ноябре — возобновить 1 ноября",
        life=12,
    ),
    P(
        "lab",
        "staff_education",
        "Учебная лаборатория ДЗЗ в вузе",
        "abdullaeva",
        start=-60,
        due=90,
        status=ProjectStatus.ON_HOLD,
        reason="Ждём решения вуза о помещении",
        life=30,
    ),
    P(
        "glossary",
        "standard",
        "Терминологический стандарт ДЗЗ",
        "yusupova",
        start=-200,
        due=-10,
        status=ProjectStatus.DONE,
        life=10,
        tasks=(2, 2),
    ),
    P(
        "hydro",
        "higher_authority_order",
        "Поручение по мониторингу водохранилищ",
        "karimov",
        start=-70,
        due=-8,
        status=ProjectStatus.DONE,
        life=8,
        tasks=(2, 2),
    ),
    P(
        "legacy",
        "platform",
        "Прежний портал спутниковых данных",
        "tursunov",
        start=-300,
        due=-40,
        status=ProjectStatus.CANCELLED,
        reason="Заменён геопорталом агентства",
        life=40,
    ),
]

# Дни создания задач Пульта совпадают с тишиной их проектов на экране: засуха — 10,
# портал — 8, посевы — 7. Ни одна задача не моложе тишины своего проекта: иначе проект
# ожил бы, и ступень на сервере разошлась бы с утверждённой.
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
        closed_after_visit=True,
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

NEW_PROJECT = "Пилот с Минздравом: мониторинг вспышек"


async def _codes(
    session: AsyncSession, model: type[ProjectTypeRef] | type[TaskTypeRef]
) -> dict[str, uuid.UUID]:
    """Код справочника → идентификатор. Сначала список: `dict(результат)` принимает результат
    SQLAlchemy за словарь — у него есть `keys()` — и падает."""
    rows = await session.execute(select(model.code, model.id))
    return dict(rows.tuples().all())


async def _names(
    session: AsyncSession, model: type[Direction] | type[Region]
) -> dict[str, uuid.UUID]:
    """Русское название → идентификатор: экран называл направление и регион словами."""
    rows = await session.execute(select(model.name_ru, model.id))
    return dict(rows.tuples().all())


async def _templates(session: AsyncSession) -> dict[str, list[Step]]:
    """Шаблоны вех по коду типа — из справочника, а не из `app.seed`.

    Справочник правит помощник (ТЗ 3.9), и проект, заведённый демо, обязан получить те же
    вехи, что получил бы заведённый им самим.
    """
    rows = await session.execute(
        select(
            ProjectTypeRef.code,
            ProjectTypeMilestone.name_ru,
            ProjectTypeMilestone.offset_days,
            ProjectTypeMilestone.sort_order,
        )
        .join(ProjectTypeRef, ProjectTypeRef.id == ProjectTypeMilestone.project_type_id)
        .order_by(ProjectTypeRef.code, ProjectTypeMilestone.sort_order)
    )
    templates: dict[str, list[Step]] = {}
    for code, title, offset, order in rows:
        templates.setdefault(code, []).append(Step(title, offset, order))
    return templates


def _marks_of(spec: P, template: list[Step]) -> list[tuple[int, M]]:
    """Вехи проекта с порядком — по правилу экрана (`milestonesFor`).

    Пройдено то, чей срок давно позади; у завершённого проекта — всё. Прошли на два дня
    позже срока: вехи из шаблона на экране так и выглядели.
    """
    if spec.marks:
        return [((index + 1) * 10, mark) for index, mark in enumerate(spec.marks)]
    finished = spec.status is ProjectStatus.DONE
    marks = []
    for step in template:
        due = spec.start + step.offset
        passed = finished or due < -3
        marks.append(
            (step.order, M(step.title, due, passed_ago=max(-due - 2, 0) if passed else None))
        )
    return marks


def _moment(day: date, zone: ZoneInfo, hours: int = 18) -> datetime:
    """Срок задачи — конец рабочего дня по Ташкенту, хранится в UTC (инвариант 8)."""
    return datetime.combine(day, time(hours), zone).astimezone(UTC)


async def before_visit(session: AsyncSession, *, now: datetime, zone: ZoneInfo) -> dict[str, int]:
    """Всё, что было до прошлого визита руководителя. Возвращает число заведённого."""
    today = local_date(now, zone)

    def ago(days: int) -> datetime:
        return now - timedelta(days=days)

    def on(days: int) -> date:
        return today + timedelta(days=days)

    types = await _codes(session, ProjectTypeRef)
    task_types = await _codes(session, TaskTypeRef)
    templates = await _templates(session)
    directions = await _names(session, Direction)
    regions = await _names(session, Region)
    center = await session.scalar(
        select(Organization).where(Organization.is_founded_by_agency.is_(True)).limit(1)
    )
    if not types or center is None:
        raise RuntimeError("справочников нет — сначала make seed")

    people = {key: Person(full_name=name, created_at=ago(365)) for key, name in PEOPLE.items()}
    session.add_all(people.values())
    partner = Organization(name=PARTNER, kind=OrganizationKind.MINISTRY.value, created_at=ago(90))
    session.add(partner)
    await session.flush()

    # Проект заведён в систему, когда начался, — но не позже последнего движения по нему.
    # Тишина задаётся правкой проекта: сервер берёт её самым свежим моментом (см. модуль).
    born = {spec.key: max(-spec.start, spec.life) for spec in PROJECTS}
    year = today.year
    projects: dict[str, Project] = {}
    # Идентификатор подпроекту нужен родительский, а его выдаёт база
    # (`app.repos.base.UUIDPrimaryKey`): сначала сохраняются проекты без родителя.
    for children in (False, True):
        for number, spec in enumerate(PROJECTS, start=1):
            if (spec.parent is not None) is not children:
                continue
            projects[spec.key] = Project(
                code=f"PRJ-{year}-{number:03d}",
                title=spec.title,
                project_type_id=types[spec.type],
                parent_project_id=projects[spec.parent].id if spec.parent else None,
                is_multiyear=spec.multiyear,
                started_on=on(spec.start),
                # Перенесённый срок заводится первым значением и переносится после визита.
                due_on=on(spec.original if spec.original is not None else spec.due),
                original_due_on=on(spec.original if spec.original is not None else spec.due),
                status_code=spec.status.value,
                status_reason=spec.reason,
                responsible_person_id=people[spec.who].id,
                direction_id=directions.get(spec.direction) if spec.direction else None,
                region_id=regions.get(spec.region) if spec.region else None,
                impediment=spec.impediment[0] if spec.impediment else None,
                impediment_updated_at=ago(spec.impediment[1]) if spec.impediment else None,
                created_at=ago(born[spec.key]),
                updated_at=ago(spec.life) if spec.life < born[spec.key] else None,
            )
            session.add(projects[spec.key])
        await session.flush()

    # Головное ведомство чужое: без движения с его стороны строка встаёт на ступень
    # «зависит от чужих», а не «молчит». У станции оно тоже чужое, но перенос её срока —
    # движение, и она идёт по плану: одно правило, два разных исхода.
    session.add_all(
        ProjectOrganization(
            project_id=projects[spec.key].id,
            organization_id=partner.id,
            role=OrganizationRole.LEAD_AGENCY.value,
        )
        for spec in PROJECTS
        if spec.lead_outside
    )
    session.add_all(
        ProjectOrganization(
            project_id=projects[spec.key].id, organization_id=center.id, role=spec.center.value
        )
        for spec in PROJECTS
        if spec.center is not None
    )

    milestones: dict[tuple[str, str], Milestone] = {}
    for spec in PROJECTS:
        for order, mark in _marks_of(spec, templates.get(spec.type, [])):
            passed = mark.passed_ago is not None
            milestones[(spec.key, mark.title)] = Milestone(
                project_id=projects[spec.key].id,
                title=mark.title,
                due_on=on(mark.original if mark.original is not None else mark.due),
                original_due_on=on(mark.original if mark.original is not None else mark.due),
                is_passed=passed,
                passed_on=on(-mark.passed_ago) if mark.passed_ago is not None else None,
                sort_order=order,
                # Вехи приходят из шаблона вместе с проектом; дата прохождения — поле, а не
                # правка: иначе веха, пройденная неделю назад, оживила бы молчащий проект.
                created_at=ago(born[spec.key]),
            )
    session.add_all(milestones.values())

    tasks: dict[str, Task] = {}

    def add_task(key: str, **fields: object) -> Task:
        task = Task(code=f"TSK-{year}-{len(tasks) + 1:04d}", **fields)
        tasks[key] = task
        return task

    for work in TASKS:
        due = _moment(on(work.due), zone)
        add_task(
            work.key,
            title=work.title,
            task_type_id=task_types.get(work.kind),
            project_id=projects[work.project].id if work.project else None,
            assignee_person_id=people[work.who].id,
            status=TaskStatus.IN_PROGRESS.value,
            due_at=due,
            original_due_at=due,
            created_at=ago(work.created),
        )

    # Задачи без имени — ровно столько, чтобы «сделано N из M» сошлось с экраном после
    # визита. Сроков у них нет: срок дал бы строку «горит» или «просрочено», а строки Пульта
    # со сроками заданы выше. Движение — не свежее тишины проекта, поэтому у молчащего
    # проекта они молчат вместе с ним (см. модуль).
    for spec in PROJECTS:
        own = [work for work in TASKS if work.project == spec.key]
        closed = sum(work.closed_after_visit for work in own)
        done, total = spec.tasks
        extra_done = done - closed
        extra_open = total - done - (len(own) - closed)
        assert extra_done >= 0 and extra_open >= 0, spec.key
        for index in range(extra_done + extra_open):
            titles = WORK_BY_TYPE[spec.type]
            common = {
                "title": titles[index % len(titles)],
                "task_type_id": task_types.get("other"),
                "project_id": projects[spec.key].id,
                "assignee_person_id": people[spec.who].id,
            }
            if index < extra_done:
                closed_days = min(born[spec.key], spec.life + 7 * index)
                add_task(
                    f"{spec.key}-done-{index}",
                    **common,
                    status=TaskStatus.DONE.value,
                    completed_at=ago(closed_days),
                    created_at=ago(min(born[spec.key], closed_days + 14)),
                    updated_at=ago(closed_days),
                )
            else:
                add_task(
                    f"{spec.key}-open-{index}",
                    **common,
                    status=TaskStatus.IN_PROGRESS.value,
                    created_at=ago(spec.life),
                )
    session.add_all(tasks.values())
    await session.flush()

    leader = await session.scalar(select(User).where(User.role == "leader"))
    decided_by = leader.id if leader else None

    session.add_all(
        LeaderQuestion(
            target_type="project",
            target_id=projects[spec.key].id,
            text=spec.question[0],
            created_at=ago(spec.question[1]),
        )
        for spec in PROJECTS
        if spec.question
    )
    session.add_all(
        [
            LeaderQuestion(
                target_type="milestone",
                target_id=milestones[("mission", "Согласование ТЗ на спутниковую группировку")].id,
                text="Утвердить перенос вехи на две недели: поставщик задерживает документацию?",
                created_at=ago(6),
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
                target_id=milestones[("portal", "Приёмка опытного образца платформы")].id,
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


async def _milestone(session: AsyncSession, project: Project, title: str) -> Milestone:
    """Веха по названию внутри проекта: вехи из шаблонов называются одинаково у многих."""
    found = await session.scalar(
        select(Milestone).where(Milestone.project_id == project.id, Milestone.title == title)
    )
    assert found is not None, title
    return found


async def _task(session: AsyncSession, title: str) -> Task:
    found = await session.scalar(select(Task).where(Task.title == title))
    assert found is not None, title
    return found


async def after_visit(session: AsyncSession, *, now: datetime, zone: ZoneInfo) -> None:
    """То, что случилось после прошлого визита: это и увидит «С прошлого визита».

    Правки идут через объекты, а не запросом `UPDATE`: журнал пишется сессией
    (`app.services.audit`), и перенос мимо неё не стал бы переносом ни для Пульта, ни для
    карточки проекта.
    """
    today = local_date(now, zone)

    def on(days: int) -> date:
        return today + timedelta(days=days)

    portal = await _project(session, "Геопортал агентства")
    acceptance = await _milestone(session, portal, "Приёмка опытного образца платформы")
    # Два переноса, а не один: «Держим ли мы свои сроки?» показывает веху, которую
    # продлевают хронически, — с первого срока через промежуточный к сроку экрана.
    acceptance.due_on = on(-16)
    await session.flush()
    acceptance.due_on = on(-9)

    for spec in PROJECTS:
        if spec.original is not None:
            moved = await _project(session, spec.title)
            moved.due_on = on(spec.due)

    upload = await _task(session, "Выгрузка данных в субплатформу")
    upload.due_at = _moment(on(5), zone)

    mission = await _project(session, "Спутниковая миссия «Навоий-2»")
    draft = await _milestone(session, mission, "Разработка ТЗ")
    draft.is_passed = True
    draft.passed_on = today

    for work in TASKS:
        if work.closed_after_visit:
            report = await _task(session, work.title)
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
    templates = await _templates(session)
    count = await session.scalar(select(func.count()).select_from(Project)) or 0
    pilot = Project(
        code=f"PRJ-{today.year}-{count + 1:03d}",
        title=NEW_PROJECT,
        project_type_id=types["industry_pilot"],
        started_on=today,
        due_on=on(120),
        original_due_on=on(120),
        status_code=ProjectStatus.IN_PROGRESS.value,
        responsible_person_id=responsible.id if responsible else None,
    )
    session.add(pilot)
    await session.flush()
    # Вехи — из шаблона, как у проекта, заведённого с экрана. В «С прошлого визита» они не
    # попадают (`app.domain.pult.classify`): там одна строка «новый проект».
    session.add_all(
        Milestone(
            project_id=pilot.id,
            title=step.title,
            due_on=on(step.offset),
            original_due_on=on(step.offset),
            sort_order=step.order,
        )
        for step in templates.get("industry_pilot", [])
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
            added = await before_visit(session, now=datetime.now(UTC), zone=zone)

        async for session in session_scope():
            await after_visit(session, now=datetime.now(UTC), zone=zone)
    finally:
        await dispose_database()

    logger.info("demo_loaded", **added)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
