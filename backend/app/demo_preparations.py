"""Вымышленные доклады и мероприятия — для превью и разработки.

Загружается из `app.demo.before_visit` после писем: запросы сведений ждут ответа от
организаций, которые завели Ижро и «Взаимодействие». Набор показывает всё, на что отвечает
раздел: доклад, где не хватает сведений и кто-то задерживает; горящий показ; подготовку,
которую пора начинать; прошедшее мероприятие.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.preparations import Addressee, PreparationKind, PrepStage
from app.repos.models import (
    InfoRequest,
    Organization,
    Person,
    Preparation,
    PreparationItem,
    Project,
)


@dataclass(frozen=True, slots=True)
class R:
    """Запрос сведений: что, от кого (ключ сотрудника или название организации), срок."""

    what: str
    person: str | None = None
    organization: str | None = None
    due: int | None = None
    received: int | None = None


@dataclass(frozen=True, slots=True)
class Prep:
    kind: PreparationKind
    title: str
    show: int
    stage: PrepStage
    who: str
    start: int | None = None
    addressee: Addressee | None = None
    project: str | None = None
    items: tuple[tuple[str, bool], ...] = ()
    requests: tuple[R, ...] = ()
    moved: int = -2


PREPARATIONS = [
    Prep(
        PreparationKind.REPORT,
        "Об итогах космического мониторинга засухи",
        show=9,
        start=-10,
        stage=PrepStage.DATA,
        who="rakhimov",
        addressee=Addressee.CABINET,
        project="geodata",
        items=(
            ("Тезисы согласованы с руководителем", True),
            ("Карты по областям", True),
            ("Таблица потерь урожая", False),
            ("Проект доклада", False),
            ("Презентация на 10 слайдов", False),
        ),
        requests=(
            R("Данные о засухе по областям за сезон", organization="Министерство экологии", due=-4),
            R("Карты засушливых районов", organization="Центр", due=-1),
            R("Справка о водных ресурсах", person="yusupova", due=-5, received=-2),
        ),
        moved=-1,
    ),
    Prep(
        PreparationKind.EVENT,
        "Международный конгресс по космическим технологиям",
        show=40,
        start=-30,
        stage=PrepStage.DRAFT,
        who="abdullaeva",
        items=(
            ("Программа конгресса", True),
            ("Список приглашённых", False),
            ("Площадка и техника", False),
        ),
        requests=(
            R("Список участников от ООН", organization="UNOOSA", due=10),
            R(
                "Тезисы выступления министерства",
                organization="Министерство цифровых технологий",
                due=15,
            ),
        ),
        moved=-3,
    ),
    Prep(
        PreparationKind.REPORT,
        "Ежеквартальная справка для Администрации Президента",
        show=3,
        start=-20,
        stage=PrepStage.APPROVAL,
        who="karimov",
        addressee=Addressee.ADMINISTRATION,
        items=(("Справка", True), ("Приложения", True), ("Согласование", False)),
        requests=(R("Показатели Центра за квартал", organization="Центр", due=-6, received=-7),),
        moved=-1,
    ),
    Prep(
        PreparationKind.REPORT,
        "О ходе программы спутниковой группировки",
        show=20,
        start=-2,
        stage=PrepStage.THESES,
        who="tursunov",
        addressee=Addressee.PRIME_MINISTER,
        moved=-6,
    ),
    Prep(
        PreparationKind.EVENT,
        "Презентация геопортала для министерств",
        show=-6,
        start=-30,
        stage=PrepStage.SHOWN,
        who="tursunov",
        project="portal",
        items=(("Демонстрационный стенд", True), ("Раздаточные материалы", True)),
        moved=-6,
    ),
]


async def load(
    session: AsyncSession,
    *,
    now: datetime,
    zone: ZoneInfo,
    people: dict[str, Person],
    projects: dict[str, Project],
) -> int:
    """Заводит подготовки; возвращает их число."""
    today = now.astimezone(zone).date()

    def on(days: int) -> date:
        return today + timedelta(days=days)

    def at(days: int) -> datetime:
        return datetime.combine(on(days), time(11, 0), tzinfo=zone)

    async def organization(name: str) -> Organization:
        # «Центр» — организация, учреждённая агентством: её название в справочнике длинное.
        condition = (
            Organization.is_founded_by_agency.is_(True)
            if name == "Центр"
            else (Organization.name == name) | (Organization.short_name == name)
        )
        found = await session.scalar(select(Organization).where(condition).limit(1))
        if found is None:
            raise RuntimeError(f"нет организации «{name}»")
        return found

    for spec in PREPARATIONS:
        moment = at(spec.moved)
        preparation = Preparation(
            kind=spec.kind.value,
            title=spec.title,
            show_on=on(spec.show),
            start_on=on(spec.start) if spec.start is not None else None,
            addressee=spec.addressee.value if spec.addressee else None,
            responsible_person_id=people[spec.who].id,
            stage=spec.stage.value,
            project_id=projects[spec.project].id if spec.project else None,
            created_at=moment,
        )
        session.add(preparation)
        await session.flush()
        session.add_all(
            PreparationItem(
                preparation_id=preparation.id,
                text=text,
                is_done=done,
                sort_order=order,
                created_at=moment,
            )
            for order, (text, done) in enumerate(spec.items, start=1)
        )
        for request in spec.requests:
            org = await organization(request.organization) if request.organization else None
            session.add(
                InfoRequest(
                    preparation_id=preparation.id,
                    what=request.what,
                    source_person_id=people[request.person].id if request.person else None,
                    source_organization_id=org.id if org else None,
                    due_on=on(request.due) if request.due is not None else None,
                    received_on=on(request.received) if request.received is not None else None,
                    created_at=moment,
                )
            )
    await session.flush()
    return len(PREPARATIONS)
