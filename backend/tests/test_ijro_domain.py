"""Домен «Ижро»: разбор без базы и без сети (ORB-102).

Здесь нет ни подключения к PostgreSQL, ни приложения: функции чистые, и проверка их
поведения не должна зависеть от того, поднято ли окружение. Это же требует контракт слоёв
— `domain` не знает ни про SQLAlchemy, ни про FastAPI.

Образцы взяты из настоящих контрольных таблиц заказчика, но **обезличены**: номера
документов вымышлены, фамилии заменены. В CI настоящих файлов нет и быть не должно
(репозиторий публичный), поэтому здесь проверяются **формы**, а совпадение с живыми
данными проверяется прогоном руками — его результат записан в карточке тикета.

Формы подобраны не на глаз: они сняты со всех 165 строк и покрывают каждую встреченную
разновидность, включая те три, из-за которых правила пришлось уточнять.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domain.ijro import (
    DuePrecision,
    DueYearSource,
    IjroState,
    band_sort_key,
    due_precision_for,
    extract_band,
    is_burning,
    is_overdue,
    normalize_document_code,
    normalize_person_name,
    normalize_spaces,
    parse_due,
    split_responsible,
)

COARSE = frozenset({(12, 25)})
"""Отчётные даты из настроек. В тестах — то же, что сегодня в системе: только 25 декабря."""


class TestBandExtraction:
    """Пункт — часть ключа повтора. Ошибка здесь задваивает реестр на первом же привозе."""

    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            ("5.1-банд", "5.1-банд"),
            ("9.а-банд", "9.а-банд"),
            ("7.а.2-банд", "7.а.2-банд"),
            ("7.б.-банд", "7.б.-банд"),
            ("5-банд.", "5-банд"),
            ("23-банд Космик мониторинг орқали", "23-банд"),
            ("2-илова 9-банд Бирламчи маълумотлар", "2-илова 9-банд"),
            ("5-илова 80.2-банд", "5-илова 80.2-банд"),
            ("7-илова 26.2-банд Лалми ва яйлов", "7-илова 26.2-банд"),
            ("Илова 85-банд", "Илова 85-банд"),
            ("3-модда (13.2-банд) Ўзбекистон", "3-модда (13.2-банд)"),
            ("16.8-модда", "16.8-модда"),
            ("18.б-банд (б) Хитой, Корея", "18.б-банд"),
        ],
    )
    def test_the_designator_is_taken_whole(self, content: str, expected: str) -> None:
        assert extract_band(content) == expected

    def test_a_year_in_the_text_is_not_swallowed(self) -> None:
        """«Банд» закрывает обозначение, и год из содержания в пункт не попадает.

        В данных три строки вида «4-илова 11.1-банд 2024 йил 6 ноябрда имзоланган…».
        Без этого правила пунктом становилось бы «4-илова 11.1-банд 2024», и та же строка
        на следующей неделе приехала бы с другим ключом — то есть как новая.
        """
        assert extract_band("4-илова 11.1-банд 2024 йил 6 ноябрда") == "4-илова 11.1-банд"

    def test_a_bare_number_after_a_designator_is_content(self) -> None:
        """«2-илова 12.3 “Ўзбеккосмос”…» — пункт кончается на 12.3."""
        assert extract_band("2-илова 12.3 “Ўзбеккосмос” агентлиги") == "2-илова 12.3"

    def test_a_non_breaking_space_does_not_break_anything(self) -> None:
        """В данных обозначение отделено неразрывным пробелом: «3.3. Белгилансинки»."""
        assert extract_band("3.3. Белгилансинки:") == "3.3"

    def test_a_row_without_a_designator_is_legal(self) -> None:
        """Одна строка из 165 начинается прямо с содержания.

        Пусто — состояние, а не ошибка: запрет выбросил бы её из реестра целиком.
        """
        assert extract_band("Ҳудудларда жамоатчилик фикри асосида шаклланган") is None


class TestBandSorting:
    def test_nine_comes_before_ten(self) -> None:
        """По самому пункту сортировка врёт: «2.10» строкой меньше «2.9».

        Карточка документа открывается, чтобы увидеть картину целиком, и пункты не по
        порядку делают её нечитаемой.
        """
        assert band_sort_key("2.9-банд") < band_sort_key("2.10-банд")

    def test_letters_survive(self) -> None:
        assert band_sort_key("7.а-банд") < band_sort_key("7.б-банд")

    def test_an_empty_band_sorts_first_and_does_not_explode(self) -> None:
        assert band_sort_key(None) == ""


class TestPersonNames:
    """29 написаний на ~20 человек. Показатель загрузки строится на этой склейке."""

    @pytest.mark.parametrize(
        ("left", "right"),
        [
            ("X. Рахмонов", "Х. Рахмонов"),  # латинская X против кириллической Х
            ("Х.Рахмонов", "Х. Рахмонов"),  # инициал без пробела
            ("K. Эрматов", "Қ. Эрматов"),  # латинская K против узбекской Қ
            ("А.  Шакиров", "А. Шакиров"),  # двойной пробел
        ],
    )
    def test_mechanical_differences_are_folded(self, left: str, right: str) -> None:
        assert normalize_person_name(left) == normalize_person_name(right)

    def test_a_different_initial_is_a_different_person(self) -> None:
        """`Ш. Арибжанов` — не `А. Арибжанов`, и в данных есть оба.

        Этот тест стоит здесь ради одной строки из 165. Любое правило склейки по фамилии
        соединит их **молча**, и показатель «кто перегружен» начнёт врать, не подав виду.
        Цена ошибки — решение руководителя по неверной картине; цена отказа склеивать —
        одно подтверждение человеком при первом привозе.
        """
        assert normalize_person_name("Ш. Арибжанов") != normalize_person_name("А. Арибжанов")

    def test_uzbek_vowel_variation_is_not_folded_automatically(self) -> None:
        """`Арибжанов` и `Арибжонов` — разные ключи.

        Скорее всего это один человек, но «скорее всего» здесь недостаточно: узбекская
        вариативность «а/о» в фамилиях настоящая. Сводит их человек, и его выбор
        запоминается псевдонимом.
        """
        assert normalize_person_name("А. Арибжанов") != normalize_person_name("А. Арибжонов")


class TestLeadExecutor:
    """«Асосий ижрочи» — 55 строк из 165, и это главный источник срыва."""

    def test_the_marker_on_its_own_line_is_found(self) -> None:
        ours, theirs = split_responsible("А.Шакиров Асосий ижрочи: Сув хўжалик вазирлиги")
        assert ours == "А.Шакиров"
        assert theirs == "Сув хўжалик вазирлиги"

    def test_the_marker_glued_to_the_name_is_found_too(self) -> None:
        """Вторая форма — половина случаев, и разбор по абзацам её пропустил бы."""
        ours, theirs = split_responsible("А. Арибжанов Асосий ижрочи: Рақамли технологиялар")
        assert ours == "А. Арибжанов"
        assert theirs == "Рақамли технологиялар"

    def test_without_the_marker_the_whole_cell_is_ours(self) -> None:
        assert split_responsible("Ш. Пардаев") == ("Ш. Пардаев", None)


class TestDocumentCode:
    """59 документов на 164 поручения — склейка написаний держится на этом ключе."""

    @pytest.mark.parametrize(
        ("left", "right"),
        [
            ("Фармон ПФ-155-сон 14.10.2024 й", "Фармон ПФ-155 14.10.2024"),
            ("Қарор ВМҚ-135 31.03.2026", "ВМҚ-135 31.03. 2026"),
            ("Фармон ПФ-130-сон 12.08.2025 й", "Фармон ПФ-130-сон 12.08.2025й"),
            ("Қарор ПҚ-99-сон 13.03.2026 й", "ҚарорПҚ-99-сон13.03.2026й"),
        ],
    )
    def test_spellings_of_one_document_give_one_key(self, left: str, right: str) -> None:
        assert normalize_document_code(left) == normalize_document_code(right)

    def test_different_documents_stay_apart(self) -> None:
        """ПФ-68 и ВМҚ-202 выпущены в один день — это не повод считать их одним."""
        assert normalize_document_code("Фармон ПФ-68 24.04.2026") != normalize_document_code(
            "ВМҚ-202 24.04.2026"
        )

    def test_a_number_without_a_recognisable_kind_still_gets_a_key(self) -> None:
        """12 ячеек из 165 не содержат вида документа вовсе.

        Белый список видов потерял бы 8 % реестра, поэтому запасной путь — не исключение,
        а норма: строка приводится к канону как есть.
        """
        assert normalize_document_code("02-1671xdfu 1.06.2026") != ""


class TestDueDate:
    """Года в источнике нет ни в одной строке."""

    def test_the_year_comes_from_the_table_header(self) -> None:
        assert parse_due("25 декабрь", table_year=2026) == (
            date(2026, 12, 25),
            DueYearSource.FROM_HEADER,
        )

    def test_the_month_comes_from_the_cell_not_from_the_block(self) -> None:
        """Пять строк из 165 стоят под чужим разделителем.

        «25 август» под блоком «СЕНТЯБРЬ» — это перенесённая просрочка, самая ценная
        строка в таблице. Правило «месяц из разделителя» выдало бы ей придуманный срок,
        то есть стёрло бы ровно то, ради чего реестр и смотрят.
        """
        parsed = parse_due("25 август", table_year=2026, block_month=9)

        assert parsed == (date(2026, 8, 25), DueYearSource.FROM_BLOCK)

    def test_a_month_matching_its_block_is_ordinary(self) -> None:
        parsed = parse_due("30 сентябрь", table_year=2026, block_month=9)

        assert parsed == (date(2026, 9, 30), DueYearSource.FROM_HEADER)

    def test_a_soft_sign_is_optional(self) -> None:
        assert parse_due("1 октябр", table_year=2026) == parse_due("1 октябрь", table_year=2026)

    def test_an_impossible_date_is_not_guessed(self) -> None:
        """31 сентября — опечатка источника. Гадать за него нельзя: срок попадёт в отчёт."""
        assert parse_due("31 сентябрь", table_year=2026) is None

    def test_a_cell_without_a_date_gives_nothing(self) -> None:
        assert parse_due("муддатсиз", table_year=2026) is None


class TestDuePrecision:
    """56 поручений из 165 стоят на 25 декабря — треть годового объёма в один день."""

    def test_the_reporting_date_is_not_an_exact_deadline(self) -> None:
        assert (
            due_precision_for(date(2026, 12, 25), coarse_dates=COARSE) is DuePrecision.END_OF_YEAR
        )

    def test_an_ordinary_date_stays_exact(self) -> None:
        assert due_precision_for(date(2026, 10, 14), coarse_dates=COARSE) is DuePrecision.EXACT

    def test_the_rule_is_a_setting_and_not_a_constant(self) -> None:
        """Заказчик скажет, что 25 октября — тоже отчётная дата, и код меняться не должен.

        Их 15, и повторяющееся «25-е» на это намекает. Зашитое в код сегодняшнее прочтение
        сделало бы следующий ответ заказчика правкой кода и новой выкладкой.
        """
        widened = frozenset({(12, 25), (10, 25)})

        assert due_precision_for(date(2026, 10, 25), coarse_dates=widened) is (
            DuePrecision.END_OF_YEAR
        )
        assert due_precision_for(date(2026, 10, 25), coarse_dates=COARSE) is DuePrecision.EXACT


class TestWhatBurns:
    TODAY = date(2026, 12, 22)

    def test_an_approaching_exact_deadline_burns(self) -> None:
        assert is_burning(
            date(2026, 12, 24),
            IjroState.IN_PROGRESS,
            DuePrecision.EXACT,
            today=self.TODAY,
            horizon_days=3,
        )

    def test_a_reporting_date_does_not_burn(self) -> None:
        """Иначе 56 строк с 25 декабря утопили бы в себе те, что горят по-настоящему."""
        assert not is_burning(
            date(2026, 12, 25),
            IjroState.IN_PROGRESS,
            DuePrecision.END_OF_YEAR,
            today=self.TODAY,
            horizon_days=3,
        )

    def test_a_finished_assignment_never_burns(self) -> None:
        assert not is_burning(
            date(2026, 12, 23),
            IjroState.DONE,
            DuePrecision.EXACT,
            today=self.TODAY,
            horizon_days=3,
        )

    def test_overdue_is_computed_and_ignores_terminal_states(self) -> None:
        past = date(2026, 12, 1)

        assert is_overdue(past, IjroState.IN_PROGRESS, today=self.TODAY)
        assert not is_overdue(past, IjroState.DONE, today=self.TODAY)
        assert not is_overdue(past, IjroState.REMOVED_FROM_CONTROL, today=self.TODAY)
        assert not is_overdue(None, IjroState.IN_PROGRESS, today=self.TODAY)


class TestSpaces:
    def test_every_kind_of_space_collapses(self) -> None:
        assert normalize_spaces("А.  Шакиров\t\n") == "А. Шакиров"
