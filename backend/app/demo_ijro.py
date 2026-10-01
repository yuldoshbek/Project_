"""Вымышленные поручения «Ижро» — тот же набор, что на утверждённом экране.

Экран раздела заказчик утвердил 30.09.2026 на вымышленных данных
(`frontend/src/sections/ijro/demo.ts` в коммите e3ee960): здесь те же четыре документа,
двадцать девять поручений, три партии привоза, контрольные отметки, продления, проблемы и
вопросы руководителю — но в базе, и считает их тот же код, что будет считать настоящие.
Загружается из `app.demo.before_visit`, до задач: три задачи «сведения по поручению» сразу
заводятся со связью (`TASK_LINKS`), а правка задачи после её создания сдвинула бы её тишину
на Пульте.

С экраном база расходится там, где правило сервера точнее или место уже занято:

- **Задачи по поручениям** — три уже знакомые задачи «Задач» (`TASK_LINKS`), а не задачи
  экрана: новые задачи со сроками встали бы строками Пульта и в «Кто перегружен?», и
  утверждённые экраны блока 1 разошлись бы с базой. Поэтому «без задач» здесь больше.
- **Промежуточная информация** не записывается (вопрос V37): у неё нет ни поля, ни
  действия на экране, и поручение, у которого на экране признак жизни — она, здесь молчит.
- **Головной исполнитель-эколог** — «Министерство экологии» Пульта, а не отдельное
  ведомство: два министерства экологии в одном справочнике запутали бы обоих.
- **Ответственная Абдуллаева Н.** — сотрудница вымышленного набора блока 1; написание из
  таблицы для несопоставленного поручения — «Н.Абдуллаева».
- **Срок «до конца года» — 25 декабря**, как в настоящих таблицах (`DuePrecision`), а не
  31-е экрана.
- **Дата продления** — дата таблицы, из которой оно пришло; продление без такой партии
  внесено вручную, и его дата — день записи.

Поручения Ижро встают строками Пульта (ТЗ 4, блок 2): горящие, просроченные, молчащие и
ждущие решения прибавляются к лестнице блока 1.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.decisions import DecisionTarget
from app.domain.dictionaries import OrganizationKind
from app.domain.ijro import (
    DocumentKind,
    DuePrecision,
    DueYearSource,
    ExtensionKind,
    IjroSource,
    IjroState,
    ImportState,
    MarkKind,
    band_sort_key,
    normalize_document_code,
)
from app.repos.models import (
    IjroAssignment,
    IjroControlMark,
    IjroDocument,
    IjroExtension,
    IjroImport,
    LeaderQuestion,
    Organization,
    Person,
    User,
)

ORGANIZATIONS = {
    "trans": ("Министерство транспорта", "Минтранс"),
    "digital": ("Министерство цифровых технологий", "Минцифры"),
}
"""Головные исполнители сверх «Министерства экологии» Пульта."""


@dataclass(frozen=True, slots=True)
class D:
    """Документ: вид, номер как в источнике, дней от выпуска, название, источник."""

    key: str
    kind: DocumentKind
    code: str
    issued: int
    title: str
    source: IjroSource


DOCUMENTS = [
    D(
        "pf155",
        DocumentKind.FARMON,
        "ПФ-155",
        -210,
        "Космик фаолиятни ривожлантириш стратегиясини амалга ошириш чора-тадбирлари тўғрисида",
        IjroSource.PA,
    ),
    D(
        "pq312",
        DocumentKind.QAROR,
        "ПҚ-312",
        -150,
        "Ерни масофадан зондлаш маълумотларидан фойдаланиш самарадорлигини ошириш "
        "чора-тадбирлари тўғрисида",
        IjroSource.PA,
    ),
    D(
        "vmq512",
        DocumentKind.QAROR,
        "ВМҚ-512",
        -95,
        "Сунъий йўлдош алоқаси инфратузилмасини ривожлантириш дастурини тасдиқлаш ҳақида",
        IjroSource.VM,
    ),
    D(
        "orq897",
        DocumentKind.QONUN,
        "ЎРҚ-897",
        -120,
        "«Космик фаолият тўғрисида»ги Қонун ижросини таъминлаш бўйича чора-тадбирлар режаси",
        IjroSource.LEGAL,
    ),
]


@dataclass(frozen=True, slots=True)
class B:
    """Партия привоза: файл, источник, дней от таблицы, классы строк (ТЗ 7)."""

    key: str
    file: str
    source: IjroSource
    table: int
    counts: dict[str, int]


BATCHES = [
    B("b1", "АП топшириқлари 2-чорак.docx", IjroSource.PA, -120, {"new": 20}),
    B("b2", "ВМ назорат жадвали.docx", IjroSource.VM, -45, {"new": 9}),
    B(
        "b3",
        "АП топшириқлари 3-чорак.docx",
        IjroSource.PA,
        -3,
        {
            "new": 2,
            "unchanged": 15,
            "text_changed": 1,
            "responsible_changed": 1,
            "due_moved": 2,
            "vanished": 1,
        },
    ),
]

LAST_CREATED = ("a19", "a22")
LAST_CHANGED = ("a05", "a13", "a20")
LAST_VANISHED = 1
"""Что изменила последняя таблица — двенадцатый вопрос (V31)."""

PENDING = ("a08", 45)
"""Неподтверждённый перенос последней партии: поручение и на сколько дней (ТЗ 7)."""


@dataclass(frozen=True, slots=True)
class X:
    """Продление: было и стало — дней от сегодня, дата таблицы — дней от сегодня."""

    due_from: int
    due_to: int
    on: int


@dataclass(frozen=True, slots=True)
class Mk:
    """Контрольная отметка: вид, дней от сегодня, роль автора, обещание, комментарий."""

    kind: MarkKind
    at: int
    author: str
    promised: int | None = None
    comment: str | None = None


Due = int | str | None
"""Дней от сегодня; `"month_end"` — конец следующего месяца; `"year_end"` — 25 декабря."""


@dataclass(frozen=True, slots=True)
class A:
    """Поручение экрана (`SPECS` в `demo.ts`): все даты — дней от сегодня."""

    key: str
    doc: str
    band: str
    content: str
    due: Due
    raw: str
    who: str | None
    stage: IjroState
    staged: int
    seen: int
    batch: str
    mechanism: str | None = None
    lead: str | None = None
    history: tuple[X, ...] = ()
    marks: tuple[Mk, ...] = ()
    problem: tuple[str, str, int] | None = None
    question: tuple[str, int] | None = None
    """Текст и сколько дней назад задан."""

    requested: bool = False


ASSIGNMENTS = [
    A(
        "a01",
        "pf155",
        "3-банд",
        "Космик технологиялар соҳасида кадрлар тайёрлаш ва малакасини ошириш дастури ишлаб "
        "чиқилсин ҳамда Вазирлар Маҳкамасига киритилсин.",
        due=-12,
        raw="А.Каримов",
        who="karimov",
        stage=IjroState.IN_PROGRESS,
        staged=-60,
        seen=-120,
        batch="b1",
        mechanism="Дастур лойиҳаси манфаатдор вазирликлар билан келишилади.",
        marks=(Mk(MarkKind.NO_ANSWER, -9, "assistant"),),
        problem=(
            "Олий таълим вазирлиги квоталар бўйича таклифларини тақдим этмади.",
            "Вазирликка қўшимча хат юбориш ва муддатни 25 октябргача узайтириш.",
            -6,
        ),
    ),
    A(
        "a02",
        "pf155",
        "5.1-банд",
        "Миллий космик дастур лойиҳаси бўйича жамоатчилик муҳокамаси ўтказилсин ва якунлари "
        "умумлаштирилсин.",
        due=-5,
        raw="Юсупова Д.",
        who="yusupova",
        stage=IjroState.NOT_STARTED,
        staged=-120,
        seen=-120,
        batch="b1",
        marks=(Mk(MarkKind.NO_ANSWER, -33, "assistant"),),
    ),
    A(
        "a03",
        "pq312",
        "2-банд",
        "Сув ҳавзалари ҳолатини космик мониторинг қилиш тартиби тўғрисидаги низом лойиҳаси ишлаб "
        "чиқилсин.",
        due=-2,
        raw="Турсунов Б.Б.",
        who="tursunov",
        stage=IjroState.IN_PROGRESS,
        staged=-40,
        seen=-120,
        batch="b1",
        mechanism="Низом лойиҳаси Экология вазирлиги билан биргаликда тайёрланади.",
        lead="eco",
        marks=(Mk(MarkKind.CONTACTED, -20, "assistant"),),
    ),
    A(
        "a04",
        "pf155",
        "7-банд",
        "Ерни масофадан зондлаш маълумотларининг ягона геопортали ишга туширилсин ва давлат "
        "органларига уланиш таъминлансин.",
        due=2,
        raw="Каримов А.А.",
        who="karimov",
        stage=IjroState.IN_PROGRESS,
        staged=-30,
        seen=-120,
        batch="b1",
        marks=(
            Mk(MarkKind.DOING, -1, "leader", promised=1, comment="Тест синовлари якунланмоқда"),
        ),
    ),
    A(
        "a05",
        "pq312",
        "4-банд",
        "Қишлоқ хўжалиги экинлари майдонларини космик суратлар асосида ҳисобга олиш бўйича "
        "услубий қўлланма тасдиқлансин.",
        due=4,
        raw="Юсупова Д.",
        who="yusupova",
        stage=IjroState.IN_PROGRESS,
        staged=-35,
        seen=-120,
        batch="b1",
        marks=(Mk(MarkKind.DOING, -18, "assistant"),),
    ),
    A(
        "a06",
        "vmq512",
        "12-банд",
        "Сунъий йўлдош алоқаси ер усти станцияларини жойлаштириш схемаси қайта ишлансин ва "
        "киритилсин.",
        due=6,
        raw="Рахимов Ш.",
        who="rakhimov",
        stage=IjroState.RETURNED,
        staged=-4,
        seen=-45,
        batch="b2",
        marks=(Mk(MarkKind.DOING, -3, "assistant"),),
    ),
    A(
        "a07",
        "vmq512",
        "1-илова 3-банд",
        "Алоқа операторлари билан сунъий йўлдош каналларидан фойдаланиш бўйича ҳамкорлик "
        "меморандуми имзолансин.",
        due=7,
        raw="Н.Абдуллаева",
        who=None,
        stage=IjroState.NOT_STARTED,
        staged=-30,
        seen=-30,
        batch="b2",
    ),
    A(
        "a08",
        "pq312",
        "6-банд",
        "Космик мониторинг маълумотлари асосида яйловлар деградацияси харитаси тайёрлансин.",
        due=10,
        raw="Юсупова Д.",
        who="yusupova",
        stage=IjroState.IN_PROGRESS,
        staged=-25,
        seen=-120,
        batch="b1",
        marks=(Mk(MarkKind.DOING, -7, "assistant"),),
        question=("Поддержать продление срока до 25 ноября?", 6),
        requested=True,
    ),
    A(
        "a09",
        "vmq512",
        "5-банд",
        "Дастурни амалга ошириш бўйича идоралараро ишчи гуруҳ таркиби тасдиқлансин.",
        due=20,
        raw="Каримов А.",
        who="karimov",
        stage=IjroState.IN_PROGRESS,
        staged=-12,
        seen=-45,
        batch="b2",
        marks=(Mk(MarkKind.CONTACTED, -3, "assistant"),),
        question=("Утвердить состав рабочей группы?", 2),
    ),
    A(
        "a10",
        "vmq512",
        "8-банд",
        "Транспорт йўлакларида навигация хизматларини ривожлантириш бўйича «йўл харитаси» ишлаб "
        "чиқилсин.",
        due=25,
        raw="Турсунов Б.",
        who="tursunov",
        stage=IjroState.IN_PROGRESS,
        staged=-40,
        seen=-45,
        batch="b2",
        lead="trans",
        marks=(Mk(MarkKind.CONTACTED, -22, "assistant"),),
    ),
    A(
        "a11",
        "pq312",
        "11-банд",
        "Ўрмон фонди ерларини космик мониторинг қилиш натижалари ҳар чоракда Вазирлар Маҳкамасига "
        "киритиб борилсин.",
        due=40,
        raw="Рахимов Ш.",
        who="rakhimov",
        stage=IjroState.NOT_STARTED,
        staged=-35,
        seen=-35,
        batch="b1",
        lead="eco",
    ),
    A(
        "a12",
        "orq897",
        "14-модда",
        "Космик фаолият субъектларининг ягона электрон реестри яратилсин ва юритилиши "
        "таъминлансин.",
        due="month_end",
        raw="Абдуллаева Н.",
        who="abdullaeva",
        stage=IjroState.IN_PROGRESS,
        staged=-50,
        seen=-120,
        batch="b1",
        lead="digital",
        marks=(Mk(MarkKind.CONTACTED, -16, "assistant"),),
    ),
    A(
        "a13",
        "pf155",
        "9-банд",
        "Космик мониторинг марказининг моддий-техника базасини мустаҳкамлаш бўйича таклифлар "
        "киритилсин.",
        due=18,
        raw="Турсунов Б.",
        who="tursunov",
        stage=IjroState.IN_PROGRESS,
        staged=-60,
        seen=-120,
        batch="b1",
        marks=(Mk(MarkKind.DOING, -25, "assistant"),),
    ),
    A(
        "a14",
        "pf155",
        "10-банд",
        "Хорижий космик агентликлар билан ҳамкорлик дастурлари рўйхати шакллантирилсин.",
        due=45,
        raw="Рахимов Ш.",
        who="rakhimov",
        stage=IjroState.NOT_STARTED,
        staged=-40,
        seen=-40,
        batch="b1",
    ),
    A(
        "a15",
        "orq897",
        "6-модда",
        "Космик фаолиятни лицензиялаш тартиби тўғрисидаги низом лойиҳаси ишлаб чиқилсин.",
        due="year_end",
        raw="Юсупова Д.",
        who="yusupova",
        stage=IjroState.IN_PROGRESS,
        staged=-70,
        seen=-120,
        batch="b1",
        history=(
            X(-90, -30, -100),
            X(-30, 0, -45),
        ),
    ),
    A(
        "a16",
        "vmq512",
        "9-банд",
        "Чекка ҳудудларни сунъий йўлдош интернети билан қамраб олиш бўйича пилот лойиҳа амалга "
        "оширилсин.",
        due=28,
        raw="Каримов А.",
        who="karimov",
        stage=IjroState.IN_PROGRESS,
        staged=-40,
        seen=-45,
        batch="b2",
    ),
    A(
        "a17",
        "pq312",
        "8-банд",
        "Космик суратлар архивини рақамлаштириш ва сақлаш тизими жорий этилсин.",
        due="year_end",
        raw="Турсунов Б.",
        who="tursunov",
        stage=IjroState.NOT_STARTED,
        staged=-21,
        seen=-21,
        batch="b1",
    ),
    A(
        "a18",
        "pf155",
        "12-банд",
        "Стратегия ижроси юзасидан йиллик ҳисобот Президент Администрациясига киритилсин.",
        due="year_end",
        raw="Каримов А.",
        who="karimov",
        stage=IjroState.IN_PROGRESS,
        staged=-20,
        seen=-120,
        batch="b1",
        marks=(Mk(MarkKind.DOING, -3, "assistant"),),
    ),
    A(
        "a19",
        "orq897",
        "9-модда",
        "Космик объектларни давлат рўйхатидан ўтказиш тартиби ишлаб чиқилсин.",
        due="year_end",
        raw="Рахимов Ш.",
        who="rakhimov",
        stage=IjroState.NOT_STARTED,
        staged=-3,
        seen=-3,
        batch="b3",
    ),
    A(
        "a20",
        "pq312",
        "10-банд",
        "Кадастр маълумотларини космик суратлар билан солиштириш натижалари бўйича ахборот "
        "тайёрлансин.",
        due=60,
        raw="Юсупова Д.",
        who="yusupova",
        stage=IjroState.IN_PROGRESS,
        staged=-50,
        seen=-120,
        batch="b1",
        history=(
            X(-40, 10, -45),
            X(10, 60, -3),
        ),
        marks=(Mk(MarkKind.DOING, -5, "assistant"),),
        problem=(
            "Кадастр агентлиги маълумотлар базасига уланиш рухсатини бермаяпти.",
            "Масалани идоралараро ишчи гуруҳ йиғилишига киритиш.",
            -5,
        ),
    ),
    A(
        "a21",
        "vmq512",
        "2-банд",
        "Дастурни молиялаштириш манбалари аниқлансин ва келгуси йил бюджети параметрларига "
        "киритилсин.",
        due="year_end",
        raw="Турсунов Б.",
        who="tursunov",
        stage=IjroState.IN_PROGRESS,
        staged=-30,
        seen=-45,
        batch="b2",
        problem=(
            "Иқтисодиёт ва молия вазирлиги лимитларни тасдиқламади.",
            "Муддатни бюджет қабул қилингунга қадар узайтириш сўралсин.",
            -2,
        ),
        requested=True,
    ),
    A(
        "a22",
        "orq897",
        "3-модда",
        "Қонун ижроси бўйича идоравий норматив ҳужжатлар рўйхати тасдиқлансин.",
        due=90,
        raw="Абдуллаева Н.",
        who="abdullaeva",
        stage=IjroState.NOT_STARTED,
        staged=-3,
        seen=-3,
        batch="b3",
    ),
    A(
        "a23",
        "pf155",
        "1-банд",
        "Стратегияни амалга ошириш бўйича «йўл харитаси» тасдиқлансин.",
        due=-30,
        raw="Каримов А.",
        who="karimov",
        stage=IjroState.SUBMITTED,
        staged=-20,
        seen=-120,
        batch="b1",
    ),
    A(
        "a24",
        "pq312",
        "1-банд",
        "Қарор ижросини ташкил этиш бўйича масъуллар белгилансин.",
        due=-45,
        raw="Юсупова Д.",
        who="yusupova",
        stage=IjroState.SUBMITTED,
        staged=-50,
        seen=-120,
        batch="b1",
    ),
    A(
        "a25",
        "vmq512",
        "3-банд",
        "Дастур кўрсаткичларининг мақсадли параметрлари ишлаб чиқилсин.",
        due=5,
        raw="Рахимов Ш.",
        who="rakhimov",
        stage=IjroState.SUBMITTED,
        staged=-8,
        seen=-45,
        batch="b2",
    ),
    A(
        "a26",
        "pf155",
        "2-банд",
        "Космик фаолият соҳасидаги норматив-ҳуқуқий ҳужжатлар хатловдан ўтказилсин.",
        due=-80,
        raw="Турсунов Б.",
        who="tursunov",
        stage=IjroState.REMOVED_FROM_CONTROL,
        staged=-70,
        seen=-120,
        batch="b1",
    ),
    A(
        "a27",
        "pq312",
        "3-банд",
        "Масофадан зондлаш маълумотларига эҳтиёж бўйича сўровнома ўтказилсин.",
        due=-40,
        raw="Рахимов Ш.",
        who="rakhimov",
        stage=IjroState.REMOVED_FROM_CONTROL,
        staged=-35,
        seen=-120,
        batch="b1",
    ),
    A(
        "a28",
        "orq897",
        "1-модда",
        "Қонуннинг мазмун-моҳияти аҳоли ўртасида тушунтирилсин.",
        due=-20,
        raw="Абдуллаева Н.",
        who="abdullaeva",
        stage=IjroState.REMOVED_FROM_CONTROL,
        staged=-15,
        seen=-120,
        batch="b1",
    ),
    A(
        "a29",
        "vmq512",
        "7-банд",
        "Ер усти станциялари учун ер участкаларини ажратиш масаласи ҳокимликлар билан ҳал этилсин.",
        due=15,
        raw="Каримов А.",
        who="karimov",
        stage=IjroState.RETURNED,
        staged=-9,
        seen=-45,
        batch="b2",
        marks=(Mk(MarkKind.CONTACTED, -2, "assistant"),),
        problem=(
            "Самарқанд вилояти ҳокимлиги ер ажратиш бўйича қарор қабул қилмади.",
            "Ҳокимликка Вазирлар Маҳкамаси номидан топшириқ хати юбориш.",
            -2,
        ),
    ),
]

TASK_LINKS = {
    "ijro-overdue": "a02",
    "ijro-report": "a18",
    "reservoirs-report": "a03",
}
"""Задачи «Задач» → поручение, из которого они выросли (ТЗ 3.2, ADR-0033)."""


def _due(spec: Due, today: date) -> tuple[date | None, DuePrecision]:
    if spec is None:
        return None, DuePrecision.EXACT
    if spec == "year_end":
        return date(today.year, 12, 25), DuePrecision.END_OF_YEAR
    if spec == "month_end":
        # Последний день следующего месяца: срок «месяцем» не оказывается в прошлом.
        first = date(today.year + today.month // 12, today.month % 12 + 1, 1)
        after = date(first.year + first.month // 12, first.month % 12 + 1, 1)
        return after - timedelta(days=1), DuePrecision.MONTH
    assert isinstance(spec, int)
    return today + timedelta(days=spec), DuePrecision.EXACT


async def load(
    session: AsyncSession,
    *,
    now: datetime,
    zone: ZoneInfo,
    people: dict[str, Person],
    partner: Organization,
) -> dict[str, uuid.UUID]:
    """Заводит раздел и возвращает поручения по ключу экрана — для связи задач."""
    today = now.astimezone(zone).date()

    def on(days: int) -> date:
        return today + timedelta(days=days)

    def at(days: int) -> datetime:
        # Середина рабочего дня по Ташкенту: дата события не уезжает на соседние сутки.
        return datetime.combine(on(days), time(11, 0), tzinfo=zone)

    users = dict((await session.execute(select(User.role, User.id))).tuples().all())
    leads = {"eco": partner}
    for key, (name, short) in ORGANIZATIONS.items():
        leads[key] = Organization(
            name=name, short_name=short, kind=OrganizationKind.MINISTRY.value, created_at=at(-200)
        )
        session.add(leads[key])

    documents = {
        spec.key: IjroDocument(
            code_norm=normalize_document_code(spec.code),
            kind=spec.kind.value,
            number_raw=spec.code,
            issued_on=on(spec.issued),
            source=spec.source.value,
            title_raw=spec.title,
            created_at=at(-130),
        )
        for spec in DOCUMENTS
    }
    session.add_all(documents.values())

    batches: dict[str, IjroImport] = {}
    for batch_spec in BATCHES:
        moved = (
            batch_spec.counts.get("text_changed", 0)
            + batch_spec.counts.get("responsible_changed", 0)
            + batch_spec.counts.get("due_moved", 0)
        )
        batches[batch_spec.key] = IjroImport(
            filename=batch_spec.file,
            sha256=hashlib.sha256(batch_spec.file.encode()).hexdigest(),
            uploaded_by=users.get("assistant"),
            uploaded_at=at(batch_spec.table),
            table_on=on(batch_spec.table),
            source=batch_spec.source.value,
            table_year=on(batch_spec.table).year,
            rows_total=sum(batch_spec.counts.values()) - batch_spec.counts.get("vanished", 0),
            rows_new=batch_spec.counts.get("new", 0),
            rows_changed=moved,
            rows_unrecognized=batch_spec.counts.get("unrecognized", 0),
            state=ImportState.APPLIED.value,
            applied_at=at(batch_spec.table),
            report={"counts": batch_spec.counts},
            created_at=at(batch_spec.table),
        )
    session.add_all(batches.values())
    await session.flush()

    by_table = {batch.table_on: batch for batch in batches.values()}
    assignments: dict[str, IjroAssignment] = {}
    for number, spec in enumerate(ASSIGNMENTS, start=1):
        due_on, precision = _due(spec.due, today)
        assignments[spec.key] = IjroAssignment(
            code=f"IJR-{today.year}-{number:03d}",
            document_id=documents[spec.doc].id,
            band=spec.band,
            band_sort=band_sort_key(spec.band),
            content=spec.content,
            mechanism=spec.mechanism,
            due_on=due_on,
            original_due_on=on(spec.history[0].due_from) if spec.history else due_on,
            due_precision=precision.value,
            due_year_source=DueYearSource.FROM_HEADER.value,
            responsible_raw=spec.raw,
            responsible_person_id=people[spec.who].id if spec.who else None,
            lead_organization_id=leads[spec.lead].id if spec.lead else None,
            is_co_executor=spec.lead is not None,
            state=spec.stage.value,
            state_changed_at=at(spec.staged),
            problem=spec.problem[0] if spec.problem else None,
            proposal=spec.problem[1] if spec.problem else None,
            problem_updated_at=at(spec.problem[2]) if spec.problem else None,
            extension_requested=spec.requested,
            import_batch_id=batches[spec.batch].id,
            first_seen_at=at(spec.seen),
            last_seen_in_import_at=at(BATCHES[-1].table),
            created_at=at(spec.seen),
        )
    session.add_all(assignments.values())
    await session.flush()

    for spec in ASSIGNMENTS:
        assignment = assignments[spec.key]
        for index, step in enumerate(spec.history):
            # Последнее продление ведёт к нынешнему сроку, каким бы он ни был по точности.
            last = index == len(spec.history) - 1
            batch = by_table.get(on(step.on))
            session.add(
                IjroExtension(
                    assignment_id=assignment.id,
                    due_from=on(step.due_from),
                    due_to=assignment.due_on if last and assignment.due_on else on(step.due_to),
                    kind=ExtensionKind.EXTENSION.value,
                    import_batch_id=batch.id if batch else None,
                    created_at=at(step.on),
                )
            )
        session.add_all(
            IjroControlMark(
                assignment_id=assignment.id,
                kind=mark.kind.value,
                promised_on=on(mark.promised) if mark.promised is not None else None,
                comment=mark.comment,
                author_id=users.get(mark.author),
                created_at=at(mark.at),
            )
            for mark in spec.marks
        )
        if spec.question:
            session.add(
                LeaderQuestion(
                    target_type=DecisionTarget.IJRO_ASSIGNMENT.value,
                    target_id=assignment.id,
                    text=spec.question[0],
                    asked_by=users.get("assistant"),
                    created_at=at(-spec.question[1]),
                )
            )

    pending, days = PENDING
    moved_due = assignments[pending].due_on
    batches[BATCHES[-1].key].report = {
        "counts": BATCHES[-1].counts,
        "created": [str(assignments[key].id) for key in LAST_CREATED],
        "changed": [str(assignments[key].id) for key in LAST_CHANGED],
        "vanished": LAST_VANISHED,
        "pending": [
            {
                "assignment_id": str(assignments[pending].id),
                "from": moved_due.isoformat() if moved_due else None,
                "to": (moved_due + timedelta(days=days)).isoformat() if moved_due else None,
            }
        ],
    }
    await session.flush()
    return {key: assignment.id for key, assignment in assignments.items()}
