"""Проект и программа: что ими является и как считается готовность.

Здесь только правила. Ни FastAPI, ни SQLAlchemy домен не знает (CLAUDE.md, границы
слоёв), и это не формальность: одно и то же правило нужно карточке проекта, Пульту,
отчёту недели и сценарию «что если». Две реализации разойдутся в цифрах, и доверия не
будет ни к одной.

Сигналы считает не этот модуль, а `app.domain.attention`: проект попадает в лестницу
внимания наравне с задачей, вехой и поручением, и правило у них общее.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, timedelta

from app.domain.dictionaries import ProjectStatus
from app.domain.errors import RuleViolationError

MIN_READINESS = 0
MAX_READINESS = 100

TITLE_MAX_LENGTH = 300
"""Как у столбца `projects.title`: длиннее база не примет, и лучше сказать об этом словами."""

IMPEDIMENT_MAX_LENGTH = 500
"""«Что мешает» — одна строка (ТЗ 3.1). Пятьсот знаков — два абзаца: длиннее — это уже
не препятствие, а описание работы, и для него есть описание проекта."""

DEFAULT_IMPEDIMENT_STALE_DAYS = 14
"""Через сколько дней строка «что мешает» перестаёт считаться действующей проблемой.

Порог лежит в справочнике и меняется без разработчика (ТЗ 3.9) — здесь только значение
по умолчанию на случай, если строки в справочнике ещё нет.
"""

NESTING_DEPTH = 1
"""Одна ступень вложенности: у программы есть подпроекты, у подпроекта — нет (ТЗ 3.1).

Ограничение не техническое. Дерево произвольной глубины требует показа деревом, а на
телефоне дерево не читается; две ступени отвечают на вопрос «где мы по программе», а
третья уже отвечает на вопрос «как устроена работа», которого руководитель не задаёт.
"""


def impediment_is_stale(*, updated_on: date | None, today: date, stale_days: int) -> bool:
    """Устарела ли строка «что мешает».

    Запись месячной давности говорит не о препятствии, а о том, что её забыли обновить.
    Считать её за действующую проблему — значит держать на Пульте тревогу, которой,
    возможно, давно нет, и приучить не обращать на тревогу внимания.

    Счёт — календарными днями Ташкента, как у молчания и просрочки (инвариант 8), а не
    моментами: иначе плитка с «обновлено 11.09» становилась бы устаревшей в девять вечера
    и оставалась свежей в девять утра того же дня — без единой правки данных.
    """
    if updated_on is None:
        return False
    return (today - updated_on).days > stale_days


def has_active_impediment(
    *, impediment: str | None, updated_on: date | None, today: date, stale_days: int
) -> bool:
    """Есть ли действующая помеха — то, что попадает в «что мешает и кто может снять»."""
    if not (impediment or "").strip():
        return False
    return not impediment_is_stale(updated_on=updated_on, today=today, stale_days=stale_days)


def readiness(
    *, passed_milestones: int, total_milestones: int, done_tasks: int, total_tasks: int
) -> int:
    """Готовность в процентах — по закрытым вехам и задачам (ТЗ 3.1).

    **Считается, а не вводится.** Ручной процент — это поле, которое помощник обязан
    поддерживать, и первое, что перестаёт соответствовать действительности: стоимость
    ввода определяет, выживет ли продукт (ТЗ 1).

    Вехи и задачи складываются в общий счёт, а не усредняются попарно: проект с десятью
    вехами и одной задачей не должен зависеть от этой задачи наполовину.

    Проект, в котором нет ни вех, ни задач, готов на ноль, а не на сто: пустота не
    является завершённостью.
    """
    total = total_milestones + total_tasks
    if total <= 0:
        return 0
    return round((passed_milestones + done_tasks) * 100 / total)


def project_readiness(
    *,
    status: ProjectStatus,
    passed_milestones: int,
    total_milestones: int,
    done_tasks: int,
    total_tasks: int,
) -> int:
    """Готовность проекта с учётом статуса.

    Завершённый проект готов на сто, даже если в нём остались непройденные вехи: статус
    «завершён» — последнее слово помощника о работе, а забытая веха — недосмотр в данных.
    Показать у завершённого «готово 60 %» значило бы спорить с тем, кто его закрыл, и
    руководитель не понял бы, закончена работа или нет. Отменённый считается как есть:
    сколько успели сделать до отмены — осмысленный ответ.
    """
    if status is ProjectStatus.DONE:
        return MAX_READINESS
    return readiness(
        passed_milestones=passed_milestones,
        total_milestones=total_milestones,
        done_tasks=done_tasks,
        total_tasks=total_tasks,
    )


def project_lag(
    *, status: ProjectStatus, started_on: date, due_on: date, today: date, readiness_pct: int
) -> int:
    """Отставание проекта: у закрытого — ноль.

    Завершённому и отменённому отставать не от чего: план исчерпан, и число дней после
    его конца говорило бы о календаре, а не о работе.
    """
    if status.is_terminal:
        return 0
    return schedule_lag(
        started_on=started_on, due_on=due_on, today=today, readiness_pct=readiness_pct
    )


EARLIEST_DATE = date(2000, 1, 1)
LATEST_DATE = date(2100, 12, 31)
"""Горизонт дат проекта. Опечатка в годе — «9999» вместо «2026» — иначе доходила бы до
арифметики дат и заканчивалась «внутренней ошибкой», а не словами о том, что не так."""


def validate_horizon(*days: date) -> None:
    """Даты проекта и вех — в пределах разумного горизонта."""
    for day in days:
        if not EARLIEST_DATE <= day <= LATEST_DATE:
            raise RuleViolationError(
                "Дата вне допустимого горизонта",
                detail=(
                    f"{day.isoformat()}: допустимо с {EARLIEST_DATE.year} по {LATEST_DATE.year} год"
                ),
            )


def template_dates(*, started_on: date, due_on: date | None, offsets: Sequence[int]) -> list[date]:
    """Сроки вех из шаблона для нового проекта.

    По умолчанию — «через столько-то дней от начала», как записано в шаблоне. Но если
    помощник назвал срок проекта раньше последней вехи шаблона, шаблон сжимается под этот
    срок, сохраняя порядок и пропорции: веха позже срока самого проекта — не план, а
    противоречие, и проект ушёл бы в «просрочено», пока его вехи ещё «по плану». Более
    поздний срок шаблон не растягивает: длина шага шаблона — то, что помощник знает о
    работе этого типа, и лишнее время остаётся запасом в конце.
    """
    last = max(offsets, default=0)
    span = (due_on - started_on).days if due_on is not None else last
    if last <= 0 or span >= last:
        return [started_on + timedelta(days=offset) for offset in offsets]
    return [started_on + timedelta(days=offset * span // last) for offset in offsets]


def default_due_on(*, started_on: date, offsets: Iterable[int]) -> date:
    """Срок нового проекта, если его не назвали, — по последней вехе шаблона (ТЗ 3.1).

    Обязательных полей у проекта два — название и тип (ТЗ 7), а срок в базе обязателен:
    без него нет ни отставания, ни лестницы. Шаблон знает длину работы этого типа лучше,
    чем пустое поле. Тип без шаблона даёт срок в день начала — его видно как «горит», и
    помощник поправит, а не забудет.
    """
    return started_on + timedelta(days=max(offsets, default=0))


def validate_text(value: str, *, what: str) -> None:
    """Текст без нулевого символа: PostgreSQL его не хранит и отвечает ошибкой базы.

    Нулевой символ попадает в поле из вставки через буфер обмена и из выгрузок других
    систем. Без проверки здесь он доходил до базы, и человек получал «внутреннюю ошибку»
    вместо того, чтобы узнать, что в тексте лишний знак.
    """
    if "\x00" in value:
        raise RuleViolationError(f"В поле «{what}» есть недопустимый символ")


def validate_title(title: str) -> str:
    """Название без пробелов по краям; пустое и слишком длинное — отказ словами."""
    validate_text(title, what="Название")
    value = title.strip()
    if not value:
        raise RuleViolationError("Напишите название проекта")
    if len(value) > TITLE_MAX_LENGTH:
        raise RuleViolationError(f"Название длиннее {TITLE_MAX_LENGTH} символов")
    return value


def validate_program(*, is_multiyear: bool, parent_is_multiyear: bool | None) -> None:
    """Подпроект входит в программу и сам программой не бывает (ТЗ 3.1).

    `parent_is_multiyear = None` — родителя нет. Родителем бывает только программа:
    подпроекты показывает раздел «Программы», и подпроект обычного проекта не увидел бы
    никто. Программа внутри программы — это вторая ступень вложенности (`NESTING_DEPTH`).
    """
    if parent_is_multiyear is None:
        return
    if not parent_is_multiyear:
        raise RuleViolationError(
            "Подпроект входит только в программу",
            detail="у выбранного родителя не отмечено «многолетняя программа»",
        )
    if is_multiyear:
        raise RuleViolationError(
            "Программа не может входить в другую программу",
            detail="вложенность в ORBITA одноступенчатая: программа → подпроект",
        )


def clean_impediment(text: str) -> str | None:
    """«Что мешает» после правки: пустая строка — помеху сняли."""
    validate_text(text, what="Что мешает")
    value = text.strip()
    if len(value) > IMPEDIMENT_MAX_LENGTH:
        raise RuleViolationError(f"«Что мешает» длиннее {IMPEDIMENT_MAX_LENGTH} символов")
    return value or None


def schedule_lag(*, started_on: date, due_on: date, today: date, readiness_pct: int) -> int:
    """Отставание от плана в днях (ТЗ 4).

    Доля прошедшего времени минус готовность, переведённая обратно в дни. Отрицательное
    значение — опережение; оно возвращается как есть, потому что «идём с запасом» — такой
    же ответ, как «отстаём на девять дней».

    Проект длиной в день исчерпан целиком — делить на ноль нечего.
    """
    span = (due_on - started_on).days
    if span <= 0:
        return 0
    elapsed = max(0.0, (today - started_on).days / span)
    return round((elapsed - readiness_pct / 100) * span)


def validate_dates(*, started_on: date, due_on: date) -> None:
    """Срок не бывает раньше начала."""
    if due_on < started_on:
        raise RuleViolationError(
            "Плановый срок завершения не может быть раньше даты начала",
            detail=f"начало {started_on.isoformat()}, срок {due_on.isoformat()}",
        )


def validate_status_reason(*, status: ProjectStatus, reason: str | None) -> None:
    """Пауза и отмена требуют причины (ТЗ 3.1).

    Без неё через месяц никто не помнит, чего ждёт приостановленный проект, и возобновить
    его некому: причина — это то, что снимает паузу.
    """
    validate_text(reason or "", what="Причина")
    if status.requires_reason and not (reason or "").strip():
        raise RuleViolationError(
            "Для этого статуса нужно указать причину",
            detail=f"статус «{status.value}» требует заполненного поля причины",
        )


def validate_nesting(*, parent_has_parent: bool) -> None:
    """Вложенность — одна ступень (ТЗ 3.1)."""
    if parent_has_parent:
        raise RuleViolationError(
            "Подпроект нельзя вложить в подпроект",
            detail="вложенность в ORBITA одноступенчатая: программа → подпроект",
        )
