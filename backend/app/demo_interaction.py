"""Вымышленные письма и соглашения — тот же набор, что на утверждённом экране.

Экран «Взаимодействие» заказчик утвердил 01.10.2026 на вымышленных данных
(`frontend/src/sections/interaction/demo.ts` в коммите 9d5355f): здесь те же организации,
письма и соглашения, но в базе. Загружается из `app.demo.before_visit` после проектов и
поручений Ижро: письма ссылаются на них.

С экраном база расходится там, где место уже занято:

- **«Министерство экологии»** — партнёр Пульта, без короткого имени; Минтранс и Минцифры
  — те, что завели поручения Ижро (`app.demo_ijro`); Центр — организация из справочника
  (`app.seed`), а не новая;
- **проекты в карточке организации** — настоящие роли организаций в проектах демо
  (`ProjectOrganization`), а не список экрана;
- **связь письма с подготовкой доклада** не заводится: раздела «Доклады» ещё нет
  (`app.repos.models.interaction`);
- письма и соглашения встают строками Пульта (ТЗ 4, блок 2).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dictionaries import OrganizationKind
from app.domain.interaction import AgreementKind, Direction, Rating
from app.repos.models import Agreement, Letter, Organization, Person, Project

EXTRA_ORGANIZATIONS = {
    "samarkand": ("Хокимият Самаркандской области", "Самаркандский хокимият", "khokimiyat"),
    "unoosa": (
        "Управление ООН по вопросам космического пространства",
        "UNOOSA",
        "international",
    ),
    "minvuz": ("Министерство высшего образования, науки и инноваций", "Минвуз", "ministry"),
    "telecom": ("АК «Узбектелеком»", "Узбектелеком", "company"),
}
"""Организации сверх тех, что уже есть в демо и справочнике."""

EXISTING = {
    "trans": "Министерство транспорта",
    "digital": "Министерство цифровых технологий",
}
"""Заведены вымышленными поручениями Ижро (`app.demo_ijro.ORGANIZATIONS`)."""

CONTACTS = {
    "eco": ("+998 71 207-00-00", "info@eco.example.uz"),
    "trans": ("+998 71 233-00-00", None),
    "digital": (None, "office@digital.example.uz"),
    "center": ("+998 71 150-00-00", None),
    "unoosa": (None, "unoosa@example.org"),
}


@dataclass(frozen=True, slots=True)
class L:
    """Письмо экрана: все даты — в днях от сегодня."""

    key: str
    direction: Direction
    org: str
    subject: str
    number: str
    sent: int
    author: str
    due: int | None = None
    answered: int | None = None
    reply: str | None = None
    rating: Rating | None = None
    project: str | None = None
    ijro: str | None = None


OUT = Direction.OUTGOING
IN = Direction.INCOMING

_ECO = [
    ("О предоставлении данных наземных метеостанций", -150, -142, Rating.SUBSTANCE),
    ("О согласовании методики оценки засухи", -128, -116, Rating.SUBSTANCE),
    ("О доступе к реестру водных объектов", -110, -101, Rating.FORMAL),
    ("О совместной рабочей группе по мониторингу", -90, -80, None),
    ("О замечаниях к проекту положения", -70, -63, Rating.SUBSTANCE),
    ("О данных по лесному фонду за полугодие", -52, -41, None),
]
_TRANS = [
    ("О навигационном обеспечении грузовых коридоров", -160, -131, None),
    ("О доступе к данным ГЛОНАСС/GPS мониторинга", -140, -118, Rating.FORMAL),
    ("О пилотном участке трассы", -120, -95, Rating.OFF_TOPIC),
    ("О замечаниях к «дорожной карте» навигации", -100, -66, None),
    ("О составе межведомственной группы", -75, -52, Rating.FORMAL),
]

LETTERS: list[L] = [
    *(
        L(
            f"eco-{index + 1}",
            OUT,
            "eco",
            subject,
            f"03-11/{2100 + index * 37}",
            sent,
            "yusupova" if index % 2 == 0 else "rakhimov",
            answered=answered,
            reply=f"02-{1400 + index * 21}",
            rating=rating,
        )
        for index, (subject, sent, answered, rating) in enumerate(_ECO)
    ),
    L(
        "eco-7",
        OUT,
        "eco",
        "О границах водоохранных зон для космической съёмки",
        "03-11/2420",
        -26,
        "yusupova",
        due=-6,
        ijro="a03",
    ),
    L(
        "eco-in-1",
        IN,
        "eco",
        "Запрос космических снимков пастбищ Каракалпакстана",
        "04-2/887",
        -4,
        "rakhimov",
        due=3,
    ),
    *(
        L(
            f"trans-{index + 1}",
            OUT,
            "trans",
            subject,
            f"03-07/{1700 + index * 41}",
            sent,
            "tursunov",
            answered=answered,
            reply=f"11-{900 + index * 13}",
            rating=rating,
        )
        for index, (subject, sent, answered, rating) in enumerate(_TRANS)
    ),
    L(
        "trans-6",
        OUT,
        "trans",
        "О согласовании «дорожной карты» навигационных услуг",
        "03-07/1985",
        -40,
        "tursunov",
        due=-19,
        ijro="a10",
    ),
    L(
        "trans-7",
        OUT,
        "trans",
        "О данных о трафике для модели загруженности",
        "03-07/2044",
        -12,
        "tursunov",
        due=8,
    ),
    L(
        "digital-1",
        OUT,
        "digital",
        "О размещении геопортала в облаке госорганов",
        "03-09/1802",
        -60,
        "abdullaeva",
        answered=-48,
        reply="05-312",
        rating=Rating.SUBSTANCE,
        project="portal",
    ),
    L(
        "digital-in-1",
        IN,
        "digital",
        "О подключении к единому реестру космической деятельности",
        "05-1/455",
        -15,
        "abdullaeva",
        due=-2,
    ),
    L(
        "center-in-1",
        IN,
        "center",
        "Отчёт о загрузке наземной станции за квартал",
        "01-02/118",
        -6,
        "karimov",
        due=2,
        project="station",
    ),
    L(
        "center-2",
        OUT,
        "center",
        "О сроках выгрузки данных в субплатформу",
        "03-01/2301",
        -20,
        "karimov",
        answered=-17,
        reply="01-02/104",
        rating=Rating.SUBSTANCE,
    ),
    L(
        "center-in-2",
        IN,
        "center",
        "Предложения в план работ на следующий год",
        "01-02/96",
        -30,
        "karimov",
        answered=-24,
        reply="03-01/2288",
    ),
    L(
        "samarkand-1",
        OUT,
        "samarkand",
        "О выделении участка под наземную станцию",
        "03-14/1950",
        -38,
        "karimov",
        project="station",
    ),
    L(
        "unoosa-in-1",
        IN,
        "unoosa",
        "Invitation: Space Applications workshop — confirmation of participants",
        "OOSA/2026/118",
        -9,
        "rakhimov",
        due=12,
    ),
    L(
        "minvuz-1",
        OUT,
        "minvuz",
        "О квотах магистратуры по космическим технологиям",
        "03-05/1890",
        -45,
        "yusupova",
        answered=-30,
        reply="07-221",
        rating=Rating.FORMAL,
    ),
    L(
        "minvuz-2",
        OUT,
        "minvuz",
        "О стажировках студентов в Центре",
        "03-05/2210",
        -10,
        "yusupova",
        due=10,
    ),
]


@dataclass(frozen=True, slots=True)
class G:
    """Соглашение экрана: даты — в днях от сегодня; `moved` — последнее движение."""

    org: str
    kind: AgreementKind
    title: str
    signed: int
    moved: int
    who: str
    until: int | None = None
    next: str | None = None
    next_on: int | None = None


AGREEMENTS: list[G] = [
    G(
        "eco",
        AgreementKind.MEMORANDUM,
        "Меморандум о мониторинге водных ресурсов",
        -300,
        -12,
        "yusupova",
        until=430,
        next="Утвердить план совместных работ на следующий год",
        next_on=40,
    ),
    G(
        "trans",
        AgreementKind.MEMORANDUM,
        "Меморандум о навигационных услугах",
        -420,
        -134,
        "tursunov",
        until=310,
        next="Пилотный участок на трассе Ташкент — Самарканд",
    ),
    G(
        "unoosa",
        AgreementKind.MEMORANDUM,
        "Memorandum on Space Applications cooperation",
        -510,
        -201,
        "rakhimov",
        until=220,
    ),
    G(
        "telecom",
        AgreementKind.CONTRACT,
        "Договор на каналы связи наземной станции",
        -200,
        -33,
        "karimov",
        until=165,
        next="Подписать акт сверки за третий квартал",
        next_on=-5,
    ),
    G(
        "center",
        AgreementKind.CONTRACT,
        "Договор на обработку снимков",
        -150,
        -3,
        "karimov",
        until=215,
        next="Приёмка этапа «каталог снимков»",
        next_on=5,
    ),
    G(
        "minvuz",
        AgreementKind.MEMORANDUM,
        "Меморандум о подготовке кадров",
        -95,
        -20,
        "yusupova",
        until=1000,
        next="Согласовать программу стажировок",
        next_on=60,
    ),
]


async def load(
    session: AsyncSession,
    *,
    now: datetime,
    zone: ZoneInfo,
    people: dict[str, Person],
    partner: Organization,
    center: Organization,
    projects: dict[str, Project],
    assignments: dict[str, uuid.UUID],
) -> int:
    """Заводит письма и соглашения; возвращает число писем."""
    today = now.astimezone(zone).date()

    def on(days: int) -> date:
        return today + timedelta(days=days)

    def at(days: int) -> datetime:
        return datetime.combine(on(days), time(11, 0), tzinfo=zone)

    organizations: dict[str, Organization] = {"eco": partner, "center": center}
    for key, name in EXISTING.items():
        found = await session.scalar(select(Organization).where(Organization.name == name))
        if found is None:
            raise RuntimeError(f"нет организации «{name}» — сначала поручения Ижро")
        organizations[key] = found
    for key, (name, short, kind) in EXTRA_ORGANIZATIONS.items():
        organizations[key] = Organization(
            name=name, short_name=short, kind=OrganizationKind(kind).value, created_at=at(-300)
        )
        session.add(organizations[key])
    for key, (phone, email) in CONTACTS.items():
        organizations[key].phone = phone
        organizations[key].email = email
    await session.flush()

    session.add_all(
        Letter(
            direction=spec.direction.value,
            organization_id=organizations[spec.org].id,
            subject=spec.subject,
            number=spec.number,
            sent_on=on(spec.sent),
            due_on=on(spec.due) if spec.due is not None else None,
            author_person_id=people[spec.author].id,
            project_id=projects[spec.project].id if spec.project else None,
            ijro_assignment_id=assignments[spec.ijro] if spec.ijro else None,
            answered_on=on(spec.answered) if spec.answered is not None else None,
            reply_number=spec.reply,
            rating=spec.rating.value if spec.rating else None,
            created_at=at(spec.sent),
        )
        for spec in LETTERS
    )
    session.add_all(
        Agreement(
            organization_id=organizations[spec.org].id,
            kind=spec.kind.value,
            title=spec.title,
            signed_on=on(spec.signed),
            valid_until=on(spec.until) if spec.until is not None else None,
            next_step=spec.next,
            next_step_on=on(spec.next_on) if spec.next_on is not None else None,
            responsible_person_id=people[spec.who].id,
            moved_at=at(spec.moved),
            created_at=at(spec.signed),
        )
        for spec in AGREEMENTS
    )
    await session.flush()
    return len(LETTERS)
