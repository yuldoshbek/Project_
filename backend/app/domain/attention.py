"""Лестница внимания — единый порядок, в котором система показывает работу.

Это главное правило ТЗ (раздел 4) и то, ради чего существует Пульт: строки из всех
разделов выстраиваются в один порядок

    ждёт решения → просрочено → горит → зависит от чужих → молчит → по плану,

а норма сворачивается в строку «и ещё N по плану». Порядок задаёт сервер: вручную строки
не сортируются, иначе два экрана покажут одно и то же в разной очерёдности, и
руководитель перестанет доверять первой строке.

**Состояние вычисляется, а не хранится** — инвариант 1. Здесь только правило над
значениями: ни базы, ни запросов. Считает его `app.services.metrics`, и только он.

Светофор из [ADR-0005](../../../docs/adr/ADR-0005-traffic-light.md) этим заменён:
он отвечал на вопрос «насколько всё плохо», лестница отвечает на вопрос «за что браться
первым». Второй вопрос — тот, который руководитель задаёт на самом деле.
"""

from __future__ import annotations

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
    is_terminal: bool,
    awaits_decision: bool,
    due_on: date | None,
    today: date,
    last_sign_of_life: date | None,
    lead_is_outside: bool,
    burn_days: int,
    quiet_days: int,
) -> Attention | None:
    """Ступень лестницы для одной записи.

    `None` означает «в лестницу не попадает»: завершённое и отменённое из неё
    исключается целиком, иначе доля спокойного росла бы по мере закрытия работ и
    перестала бы что-либо значить.

    Порядок проверок — и есть лестница. Он важнее каждой отдельной проверки: запись,
    которая и просрочена, и молчит, показывается просроченной, потому что решение по ней
    принимают именно из-за срока.

    Все пороги приходят аргументами: они лежат в справочнике и меняются без разработчика
    (ТЗ 3.9). Сегодняшний день — тоже аргумент, а не системные часы: сроки наступают по
    Ташкенту (`app.domain.clock`).
    """
    if is_terminal:
        return None

    # Вопрос к руководителю старше срока: пока он не ответил, работать всё равно нельзя,
    # и показывать такую строку просроченной — значит требовать действия от того, кто его
    # уже сделал.
    if awaits_decision:
        return Attention.AWAITING_DECISION

    if due_on is not None:
        if due_on < today:
            return Attention.OVERDUE
        if (due_on - today).days <= burn_days:
            return Attention.BURNING

    # «Зависит от чужих» выше молчания: молчит и наш, и чужой, но позвонить в первом
    # случае и написать письмо во втором — разные действия, и первое бесполезно.
    if lead_is_outside:
        return Attention.BLOCKED_BY_OTHERS

    if last_sign_of_life is None or (today - last_sign_of_life).days > quiet_days:
        return Attention.SILENT

    return Attention.ON_TRACK


def deviation_days(
    attention: Attention,
    *,
    due_on: date | None,
    today: date,
    last_sign_of_life: date | None,
) -> int:
    """На сколько дней запись отклонилась — число рядом со ступенью (ТЗ 4).

    У каждой ступени оно означает своё, и это не путаница, а суть: у просроченного —
    сколько дней прошло после срока, у горящего — сколько осталось, у молчащего — сколько
    длится тишина. Одно число на все ступени пришлось бы объяснять подписью, а подпись на
    телефоне занимает строку.
    """
    if attention is Attention.OVERDUE and due_on is not None:
        return (today - due_on).days
    if attention is Attention.BURNING and due_on is not None:
        return (due_on - today).days
    if attention is Attention.SILENT and last_sign_of_life is not None:
        return (today - last_sign_of_life).days
    return 0


def sort_key(attention: Attention, deviation: int, due_on: date | None) -> tuple[int, int, str]:
    """Порядок строк внутри лестницы.

    Сначала ступень, потом отклонение по убыванию — самое застарелое сверху, — потом
    срок. Запись без срока уходит в конец своей ступени: у неё срок не наступает, и
    ставить её выше горящих значит прятать горящие.
    """
    return (attention.rank, -deviation, due_on.isoformat() if due_on else "9999-12-31")
