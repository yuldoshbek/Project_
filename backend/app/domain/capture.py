"""Разбор строки задачи — правила ТЗ 7: тип, срок и ответственный из одной фразы.

    «к пятнице рассмотрение проекта постановления Минэкологии, Каримов»
      → тип «Рассмотрение и визирование», срок — ближайшая пятница, ответственный Каримов А.

Разбор правилами, без внешних моделей (ТЗ 7): у каждого распознанного есть правило,
которое можно прочитать, проверить примером и назвать человеку, спросившему «почему срок
такой». Внешние модели ИИ из системы сняты (CLAUDE.md, «Чего не делать»).

Разбор только **предлагает**, решает человек. Каждое распознанное возвращается вместе с
фрагментом исходной строки (`matched_*`): экран показывает подсказку до сохранения, и её
можно поправить. Что предложила система и что внёс человек — разные вещи (инвариант 6),
и ошибка разбора не должна молча стать сроком.

Правила те же, на которых утверждён экран «Задачи»: они перенесены сюда из
`frontend/src/sections/tasks/parse.ts` вместе с его примерами (`tests/test_capture.py`).
Разбор — правило предметной области, и у экрана и у захвата с телефона оно должно быть
одно: два разборщика однажды разойдутся, и одна фраза даст два разных срока.
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

# В `re` нет `\p{L}`. «Словесный» символ без цифр и подчёркивания — это буква и ещё
# числовые знаки вроде «²» и «½». Вплотную к слову в строке задачи они не встречаются, а
# точный класс — тысяча символов в исходнике, зависящая от версии Unicode.
_LETTER = r"[^\W\d_]"
# Цифра — только ASCII, как `\d` в JavaScript: `\d` в `re` принимает цифры любой
# письменности, и строка, которую экран не понял, здесь давала бы срок.
_DIGIT = "[0-9]"

# Граница слова для кириллицы — «не буква и не цифра по соседству», как в parse.ts, а не
# `\b`: у `\b` подчёркивание — часть слова, и «_завтра» разбиралось бы иначе.
_START = rf"(?<!{_LETTER}|{_DIGIT})"
_END = rf"(?!{_LETTER}|{_DIGIT})"

# Инициал — заглавная буква кириллицы или латиницы вместе с расширенными блоками: узбекские
# Ў, Қ, Ғ, Ҳ, латинские Ž и Ş. Класс только из А-Я и A-Z сравнение с parse.ts поймало на
# «Ž.»: экран уносил инициал вместе с фамилией, а здесь он оставался в названии. Под
# IGNORECASE класс принимает и строчную — ровно как `\p{Lu}` под флагом `i` в parse.ts,
# поэтому «Каримов и. о.» теряет «и. о.» в обоих разборщиках одинаково.
_INITIAL = "[A-ZÀ-ÖØ-ÞĀ-ɏЀ-ЯѠ-ҁҊ-ԯ]"

# Предлог перед сроком — уходит из названия вместе со сроком.
_PREP = r"(?:(?:к|до|в|во|на|не позднее)\s+)?"

# Дни недели во всех падежах, в которых их говорят: «к пятнице», «в пятницу», «до среды».
# Номер — как у `date.weekday()`: неделя в Узбекистане начинается с понедельника.
_WEEKDAYS = (
    ("понедельник[аиу]?", 0),
    ("вторник[аиу]?", 1),
    ("сред[аеуы]", 2),
    ("четверг[аиу]?", 3),
    ("пятниц[аеуы]", 4),
    ("суббот[аеуы]", 5),
    ("воскресень[еяю]", 6),
)

_MONTHS = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)

_FRIDAY = 4


@dataclass(frozen=True, slots=True)
class ParsedLine:
    """Предложение разбора. Ничего из него не сохраняется без подтверждения человека.

    `matched_*` — фрагменты исходной строки ровно в том написании, в каком их нашли:
    экран подсвечивает их, чтобы было видно, откуда взялась каждая подсказка.
    """

    title: str
    type_code: str | None
    due_on: date | None
    assignee_id: object | None
    matched_type: str | None
    matched_due: str | None
    matched_assignee: str | None


def _rule(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


def _dated(today: date, day: int, month: int, year: int | None) -> date | None:
    """Дата из строки: с годом — как написана, без года — ближайшая впереди.

    «15.03», сказанное в октябре, — март следующего года, а не прошедший: срок в прошлом
    никто не ставит. Несуществующая дата («31.02») — не срок, а не тихий сдвиг на 3 марта;
    прошедшее 29.02 високосного года в следующем году не существует и тоже не срок.
    """
    if year is not None and year < 1000:
        # «05.02.0001» — опечатка, а не срок. parse.ts такой год отвергал: Date.parse не
        # читает год короче четырёх цифр (найдено сравнением с ним на случайных строках).
        # Принять его здесь — дать срок там, где утверждённый экран срока не давал.
        return None
    try:
        candidate = date(today.year if year is None else year, month, day)
        if year is None and candidate < today:
            candidate = candidate.replace(year=today.year + 1)
    except ValueError:
        return None
    return candidate


def _next_weekday(index: int) -> Callable[[re.Match[str], date], date]:
    # День недели — ближайший впереди: «в пятницу», сказанное в пятницу, — это через
    # неделю; сегодняшний срок называют словом «сегодня».
    def due(_: re.Match[str], today: date) -> date:
        return today + timedelta(days=(index - today.weekday()) % 7 or 7)

    return due


def _end_of_week(_: re.Match[str], today: date) -> date:
    # Конец недели — пятница этой недели; сказанное в пятницу — сегодня, в выходные —
    # следующая пятница: суббота и воскресенье в аппарате не рабочие.
    return today + timedelta(days=(_FRIDAY - today.weekday()) % 7)


def _end_of_month(_: re.Match[str], today: date) -> date:
    return today.replace(day=calendar.monthrange(today.year, today.month)[1])


def _numeric_date(match: re.Match[str], today: date) -> date | None:
    return _dated(today, int(match[1]), int(match[2]), int(match[3]) if match[3] else None)


def _worded_date(match: re.Match[str], today: date) -> date | None:
    month = _MONTHS.index(match[2].lower()) + 1
    return _dated(today, int(match[1]), month, int(match[3]) if match[3] else None)


# Порядок — как в parse.ts, и он значим: побеждает первое правило, давшее срок. Правило,
# чьё первое совпадение не дало даты («к 31.02»), уступает следующему правилу, а не
# своему второму совпадению.
_DUE_RULES: tuple[tuple[re.Pattern[str], Callable[[re.Match[str], date], date | None]], ...] = (
    (_rule(_START + _PREP + "послезавтра" + _END), lambda _, today: today + timedelta(days=2)),
    (_rule(_START + _PREP + "завтра" + _END), lambda _, today: today + timedelta(days=1)),
    (_rule(_START + _PREP + "сегодня" + _END), lambda _, today: today),
    (
        _rule(_START + r"через\s+([0-9]{1,3})\s+(?:дн(?:я|ей)|день)" + _END),
        lambda match, today: today + timedelta(days=int(match[1])),
    ),
    (
        _rule(_START + r"через\s+([0-9]{1,2})\s+недел[иью]" + _END),
        lambda match, today: today + timedelta(weeks=int(match[1])),
    ),
    (_rule(_START + r"через\s+неделю" + _END), lambda _, today: today + timedelta(weeks=1)),
    (_rule(_START + _PREP + r"конц[ау]\s+недели" + _END), _end_of_week),
    (_rule(_START + _PREP + r"конц[ау]\s+месяца" + _END), _end_of_month),
    (
        _rule(_START + _PREP + r"([0-9]{1,2})\.([0-9]{1,2})(?:\.([0-9]{4}))?" + _END),
        _numeric_date,
    ),
    (
        _rule(
            _START + _PREP + r"([0-9]{1,2})\s+(" + "|".join(_MONTHS) + r")(?:\s+([0-9]{4}))?" + _END
        ),
        _worded_date,
    ),
    *(
        (_rule(_START + _PREP + pattern + _END), _next_weekday(index))
        for pattern, index in _WEEKDAYS
    ),
)

# Типы задач по ключевым словам (ТЗ 3.9). Порядок важен: «внесение в Кабмин» раньше
# «согласования», потому что строка «согласовать и внести в Кабмин» — про внесение.
_TYPE_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cabinet_submission", _rule(r"кабмин|кабинет\s+министров|внес[теиё]")),
    ("ijro_report", _rule(r"ижро|сведени[яй]\s+по\s+поручени|по\s+поручению")),
    (
        "technical_spec",
        _rule(rf"(?<!{_LETTER})тз(?!{_LETTER})|техническ{_LETTER}*\s+задани"),
    ),
    ("review_and_endorse", _rule(r"рассмотр|визир")),
    ("approval", _rule(r"согласов")),
    ("analytical_note", _rule(r"справк|аналитическ|информаци")),
    ("site_visit", _rule(r"выезд|командиров|полигон")),
    ("request_or_survey", _rule(r"запрос|опрос")),
    ("subplatform_upload", _rule(r"выгруз|субплатформ")),
    ("participant_selection", _rule(r"отбор")),
)

_SPACES = re.compile(r"\s+")
_SPACE_BEFORE_MARK = re.compile(r"\s+([,.;:])")
# Висящие знаки по краям названия: остаются, когда из «справка — Юсуповой» уходит фамилия.
_EDGE = " ,.;:—–-"


def _find_due(text: str, today: date) -> tuple[date, str] | None:
    for pattern, due_of in _DUE_RULES:
        match = pattern.search(text)
        if match is None:
            continue
        due = due_of(match, today)
        if due is not None:
            return due, match[0]
    return None


def _find_type(text: str, type_codes: Collection[str]) -> tuple[str, str] | None:
    for code, pattern in _TYPE_RULES:
        match = pattern.search(text)
        if match is not None and code in type_codes:
            return code, match[0]
    return None


def _find_assignee(text: str, people: Sequence[tuple[object, str]]) -> tuple[object, str] | None:
    """Ответственный — по фамилии в любом падеже: «Каримов», «Каримову», «Юсуповой».

    Инициалы рядом уходят вместе с фамилией. Две подходящие фамилии — не угадываем:
    одинаковые фамилии склеивать нельзя (CLAUDE.md), выбор остаётся человеку.
    """
    hits: list[tuple[object, str, bool]] = []
    for person_id, name in people:
        words = name.split()
        surname = words[0].lower() if words else ""
        # Падежи женской фамилии строятся без конечной «а»: «Юсупова» → «Юсуповой», «Юсупову».
        stem = surname.removesuffix("а")
        if not stem:
            # Узнавать не по чему: пустая основа совпала бы с любым коротким словом.
            continue
        pattern = _rule(
            _START
            + "("
            + re.escape(stem)
            + _LETTER
            + "{0,3})"
            + _END
            + r"(?:\s+(?:"
            + _INITIAL
            + r"\.\s?){1,2})?"
        )
        hits.extend(
            (person_id, match[0].rstrip(), match[1].lower() == surname)
            for match in pattern.finditer(text)
        )
    if len({person_id for person_id, _, _ in hits}) == 1:
        return hits[0][0], hits[0][1]
    # Точное совпадение сильнее падежной формы: «Юсупова» — это Юсупова, а не Юсупов.
    exact = [(person_id, fragment) for person_id, fragment, is_exact in hits if is_exact]
    if len({person_id for person_id, _ in exact}) == 1:
        return exact[0]
    return None


def _title(text: str, cut: Sequence[str | None]) -> str:
    """Название — строка без срока и ответственного, с заглавной буквы и без висящих знаков.

    Слово типа в названии остаётся: «рассмотрение проекта постановления» без
    «рассмотрения» теряет смысл, а срок и фамилия и так видны в своих графах.
    """
    rest = text
    for fragment in cut:
        if fragment:
            rest = rest.replace(fragment, " ", 1)
    rest = _SPACE_BEFORE_MARK.sub(r"\1", _SPACES.sub(" ", rest)).strip(_EDGE)
    return rest[:1].upper() + rest[1:]


def parse_line(
    text: str,
    *,
    today: date,
    people: Sequence[tuple[object, str]],
    type_codes: Collection[str],
) -> ParsedLine:
    """Разбирает строку в предложение: название, тип, срок и ответственного.

    `today` — сегодняшняя дата по Ташкенту (`clock.today_in`): «завтра» наступает по
    календарю аппарата, а не по UTC (инвариант 8). `people` — пары «идентификатор, ФИО»,
    фамилия — первое слово ФИО. `type_codes` — коды из справочника типов: тип, которого
    в справочнике нет, не предлагается, даже если правило совпало.
    """
    due = _find_due(text, today)
    assignee = _find_assignee(text, people)
    task_type = _find_type(text, type_codes)
    return ParsedLine(
        title=_title(text, (due[1] if due else None, assignee[1] if assignee else None)),
        type_code=task_type[0] if task_type else None,
        due_on=due[0] if due else None,
        assignee_id=assignee[0] if assignee else None,
        matched_type=task_type[1] if task_type else None,
        matched_due=due[1] if due else None,
        matched_assignee=assignee[1] if assignee else None,
    )
