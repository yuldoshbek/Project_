"""Лестница внимания — единый порядок, в котором система показывает работу.

Это главное правило ТЗ (раздел 4) и то, ради чего существует Пульт: строки из всех
разделов выстраиваются в один порядок

    ждёт решения → просрочено → горит → зависит от чужих → молчит → по плану,

а норма сворачивается в строку «и ещё N по плану». Порядок задаёт сервер: вручную строки
не сортируются, иначе два экрана покажут одно и то же в разной очерёдности, и
руководитель перестанет доверять первой строке.

**Состояние вычисляется, а не хранится** — инвариант 1. Здесь только правило над
значениями: ни базы, ни запросов. Снимок данных собирает `app.repos.attention`, а
расчёт по нему вызывает `app.services.metrics` — и только он.

**Расчёт чистый, поэтому «что если» бесплатно.** `build_ladder` получает снимок и
возвращает лестницу; `with_due_changes` возвращает снимок с другими сроками. Сценарий
«что если» (ТЗ 5, критерий 3 блока 1) — это тот же расчёт по изменённому снимку: второго
кода нет, и записывать в базу ему нечем.

Светофор из [ADR-0005](../../../docs/adr/ADR-0005-traffic-light.md) этим заменён:
он отвечал на вопрос «насколько всё плохо», лестница отвечает на вопрос «за что браться
первым». Второй вопрос — тот, который руководитель задаёт на самом деле.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import date
from enum import StrEnum


class Signal(StrEnum):
    """Как ступень выглядит на экране.

    Четыре значения против шести ступеней — намеренно. Цветов ровно столько, сколько
    различает глаз на телефоне под солнцем, и каждый обязан нести смысл
    (`frontend/src/styles/tokens.css`). Подпись при этом у каждой ступени своя: цвет
    усиливает слово, а не заменяет его — иначе дальтоник и чёрно-белая печать отчёта
    теряют смысл строки.
    """

    CALL = "call"
    """Требует решения руководителя."""

    BURN = "burn"
    """Горит или просрочено: срок прошёл или сгорит на днях."""

    WAIT = "wait"
    """Ждём чужого: чужое ведомство или тишина ответственного."""

    CALM = "calm"
    """Идёт по плану."""


class Attention(StrEnum):
    """Ступень лестницы. Порядок объявления — и есть порядок показа."""

    AWAITING_DECISION = "awaiting_decision"
    OVERDUE = "overdue"
    BURNING = "burning"
    BLOCKED_BY_OTHERS = "blocked_by_others"
    SILENT = "silent"
    ON_TRACK = "on_track"

    @property
    def rank(self) -> int:
        """Место в лестнице: 0 — выше всех.

        Считается по порядку объявления, а не отдельной таблицей: две записи одного
        порядка разойдутся при первой вставке новой ступени между ними.
        """
        return LADDER.index(self)

    @property
    def signal(self) -> Signal:
        return _SIGNALS[self]

    @property
    def is_normal(self) -> bool:
        """Норма сворачивается в строку «и ещё N по плану» (ТЗ 4)."""
        return self is Attention.ON_TRACK


LADDER: tuple[Attention, ...] = (
    Attention.AWAITING_DECISION,
    Attention.OVERDUE,
    Attention.BURNING,
    Attention.BLOCKED_BY_OTHERS,
    Attention.SILENT,
    Attention.ON_TRACK,
)

_SIGNALS: dict[Attention, Signal] = {
    Attention.AWAITING_DECISION: Signal.CALL,
    Attention.OVERDUE: Signal.BURN,
    Attention.BURNING: Signal.BURN,
    Attention.BLOCKED_BY_OTHERS: Signal.WAIT,
    Attention.SILENT: Signal.WAIT,
    Attention.ON_TRACK: Signal.CALM,
}


def attention_of(
    *,
    awaiting_since: date | None,
    due_on: date | None,
    today: date,
    last_sign_of_life: date | None,
    lead_is_outside: bool,
    burn_days: int,
    quiet_days: int,
) -> Attention:
    """Ступень лестницы для одной незавершённой записи.

    Завершённое и отменённое в расчёт не попадает вовсе — его отсекает снимок: иначе
    доля спокойного росла бы по мере закрытия работ и перестала бы что-либо значить.

    Порядок проверок — и есть лестница. Он важнее каждой отдельной проверки: запись,
    которая и просрочена, и молчит, показывается просроченной, потому что решение по ней
    принимают именно из-за срока.

    `last_sign_of_life = None` означает «своего движения у записи нет» — так у вехи: её
    либо проходят, либо нет, и её молчание — это молчание проекта. Считать его второй
    раз значило бы показать одну тишину двумя строками.

    Все пороги приходят аргументами: они лежат в справочнике и меняются без разработчика
    (ТЗ 3.9). Сегодняшний день — тоже аргумент, а не системные часы: сроки наступают по
    Ташкенту (`app.domain.clock`).
    """
    # Вопрос к руководителю старше срока: пока он не ответил, работать всё равно нельзя,
    # и показывать такую строку просроченной — значит требовать действия от того, кто
    # ждёт его ответа.
    if awaiting_since is not None:
        return Attention.AWAITING_DECISION

    if due_on is not None:
        if due_on < today:
            return Attention.OVERDUE
        if (due_on - today).days <= burn_days:
            return Attention.BURNING

    if last_sign_of_life is not None and (today - last_sign_of_life).days > quiet_days:
        # «Зависит от чужих» — это тишина, но чужая (ТЗ 4: головной исполнитель не
        # агентство, и с его стороны нет движения). Чужое ведомство, у которого работа
        # идёт, по плану; наше молчание и чужое — разные действия: позвонить
        # ответственному или написать письмо ведомству.
        return Attention.BLOCKED_BY_OTHERS if lead_is_outside else Attention.SILENT

    return Attention.ON_TRACK


def deviation_days(
    attention: Attention,
    *,
    awaiting_since: date | None,
    due_on: date | None,
    today: date,
    last_sign_of_life: date | None,
) -> int:
    """На сколько дней запись отклонилась — число рядом со ступенью (ТЗ 4).

    У каждой ступени оно означает своё, и это не путаница, а суть: у ждущего решения —
    сколько дней ждёт, у просроченного — сколько дней после срока, у горящего — сколько
    осталось, у молчащего и зависящего от чужих — сколько длится тишина. Одно число на
    все ступени пришлось бы объяснять подписью, а подпись на телефоне занимает строку.
    """
    if attention is Attention.AWAITING_DECISION and awaiting_since is not None:
        return (today - awaiting_since).days
    if attention is Attention.OVERDUE and due_on is not None:
        return (today - due_on).days
    if attention is Attention.BURNING and due_on is not None:
        return (due_on - today).days
    if (
        attention in {Attention.SILENT, Attention.BLOCKED_BY_OTHERS}
        and last_sign_of_life is not None
    ):
        return (today - last_sign_of_life).days
    return 0


def sort_key(attention: Attention, deviation: int, due_on: date | None) -> tuple[int, int, str]:
    """Порядок строк внутри лестницы: сначала ступень, потом то, что горит сильнее.

    «Сильнее» у ступеней противоположно по знаку. У горящего отклонение — дни *до* срока,
    и первым идёт ближайший: «горит сегодня» выше «горит через шесть дней». У остальных
    отклонение — дни *после* события (срока, вопроса, последнего движения), и первым идёт
    самое застарелое. Запись без срока уходит в конец своей ступени: у неё срок не
    наступает, и ставить её выше горящих значит прятать горящие.
    """
    urgency = deviation if attention is Attention.BURNING else -deviation
    return (attention.rank, urgency, due_on.isoformat() if due_on else "9999-12-31")


@dataclass(frozen=True, slots=True)
class Item:
    """Одна незавершённая запись в снимке — всё, что нужно правилу, и ничего больше.

    Одинаковая для проекта, вехи, задачи и решения: это и есть смысл лестницы. Строка
    проекта и строка задачи различаются значением `section`, а не устройством, — иначе
    Пульт пришлось бы собирать из разных списков и сортировать их вручную.
    """

    section: str
    """Раздел, откуда запись: `projects`, `milestones`, `tasks`, `decisions`."""

    entity_id: uuid.UUID
    title: str | None
    due_on: date | None
    last_sign_of_life: date | None
    awaiting_since: date | None
    """Дата самого старого открытого вопроса к руководителю по записи; `None` — вопроса нет."""

    lead_is_outside: bool
    responsible_person_id: uuid.UUID | None
    kind: str | None = None
    """Вид записи внутри раздела — сейчас вид решения. Подпись по нему переводит
    интерфейс: код в заголовок строки не подставляется."""


@dataclass(frozen=True, slots=True)
class Row:
    """Строка лестницы внимания — то, что видит руководитель."""

    section: str
    entity_id: uuid.UUID
    title: str | None
    kind: str | None
    attention: Attention
    deviation: int
    """Число дней рядом со ступенью — см. `deviation_days`."""

    due_on: date | None
    responsible_person_id: uuid.UUID | None

    @property
    def signal(self) -> Signal:
        return self.attention.signal

    @property
    def order(self) -> tuple[int, int, str]:
        return sort_key(self.attention, self.deviation, self.due_on)


@dataclass(frozen=True, slots=True)
class Ladder:
    """Лестница целиком: строки внимания и свёрнутая норма.

    Норма не выбрасывается, а считается: ТЗ 4 требует строку «и ещё N по плану» — без неё
    руководитель не знает, десять у него проектов или двести, и первая строка теряет
    масштаб.
    """

    rows: tuple[Row, ...]
    on_track: int

    @property
    def needs_attention(self) -> int:
        return len(self.rows)

    def of(self, attention: Attention) -> tuple[Row, ...]:
        return tuple(row for row in self.rows if row.attention is attention)

    def count(self, attention: Attention) -> int:
        if attention.is_normal:
            return self.on_track
        return len(self.of(attention))


def build_ladder(items: Iterable[Item], *, today: date, burn_days: int, quiet_days: int) -> Ladder:
    """Лестница по снимку. Чистая функция: одинаковый снимок — одинаковая лестница."""
    rows: list[Row] = []
    on_track = 0

    for item in items:
        state = attention_of(
            awaiting_since=item.awaiting_since,
            due_on=item.due_on,
            today=today,
            last_sign_of_life=item.last_sign_of_life,
            lead_is_outside=item.lead_is_outside,
            burn_days=burn_days,
            quiet_days=quiet_days,
        )
        if state.is_normal:
            on_track += 1
            continue
        rows.append(
            Row(
                section=item.section,
                entity_id=item.entity_id,
                title=item.title,
                kind=item.kind,
                attention=state,
                deviation=deviation_days(
                    state,
                    awaiting_since=item.awaiting_since,
                    due_on=item.due_on,
                    today=today,
                    last_sign_of_life=item.last_sign_of_life,
                ),
                due_on=item.due_on,
                responsible_person_id=item.responsible_person_id,
            )
        )

    rows.sort(key=lambda row: row.order)
    return Ladder(rows=tuple(rows), on_track=on_track)


DueChanges = Mapping[tuple[str, uuid.UUID], date]
"""Новые сроки для «что если»: (раздел, запись) → срок."""


def with_due_changes(items: Iterable[Item], changes: DueChanges) -> tuple[Item, ...]:
    """Снимок, в котором у названных записей другие сроки.

    Возвращает новый снимок и не трогает прежний: сценарий «что если» сравнивает две
    лестницы, и исходная обязана остаться той, что есть на самом деле. Изменение записи,
    которой в снимке нет, — ошибка вызывающего кода, а не тихий пропуск: иначе «что
    если» покажет «ничего не изменилось» там, где изменение просто потерялось.
    """
    snapshot = tuple(items)
    known = {(item.section, item.entity_id) for item in snapshot}
    missing = set(changes) - known
    if missing:
        raise KeyError(f"в снимке нет записей для «что если»: {sorted(map(str, missing))}")
    return tuple(
        replace(item, due_on=changes[(item.section, item.entity_id)])
        if (item.section, item.entity_id) in changes
        else item
        for item in snapshot
    )
