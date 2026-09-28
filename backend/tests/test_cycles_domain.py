"""Годовые циклы: даты на год вперёд и ближайшая дата за горизонтом (ТЗ 3.1)."""

from datetime import date

from app.domain.cycles import CycleRule, next_date, occurrences

TODAY = date(2026, 9, 28)


def dates(rule: CycleRule, month: int, day: int, every_years: int = 1, anchor_year: int = 2026):
    return occurrences(
        rule=rule,
        month=month,
        day=day,
        every_years=every_years,
        anchor_year=anchor_year,
        since=TODAY,
    )


def test_annual_and_quarterly_unfold_one_year_ahead() -> None:
    assert dates(CycleRule.ANNUAL, 2, 15) == [date(2027, 2, 15)]
    assert dates(CycleRule.QUARTERLY, 1, 5) == [
        date(2026, 10, 5),
        date(2027, 1, 5),
        date(2027, 4, 5),
        date(2027, 7, 5),
    ]


def test_every_n_years_counts_from_anchor() -> None:
    assert dates(CycleRule.EVERY_N_YEARS, 3, 1, every_years=3, anchor_year=2027) == [
        date(2027, 3, 1)
    ]
    assert dates(CycleRule.EVERY_N_YEARS, 3, 1, every_years=3, anchor_year=2026) == []


def test_years_before_anchor_do_not_count() -> None:
    # 2027 = 2030 − 3: остаток от деления ноль, но цикл начинается только в 2030-м.
    assert dates(CycleRule.EVERY_N_YEARS, 3, 1, every_years=3, anchor_year=2030) == []


def test_missing_day_is_skipped() -> None:
    assert dates(CycleRule.ANNUAL, 2, 31) == []
    # 31-го ежеквартально: апреля 31-го нет, остальные кварталы на месте.
    assert dates(CycleRule.QUARTERLY, 1, 31) == [
        date(2026, 10, 31),
        date(2027, 1, 31),
        date(2027, 7, 31),
    ]


def test_next_date_goes_beyond_horizon() -> None:
    def upcoming(rule: CycleRule, month: int, day: int, every: int = 1, anchor: int = 2026):
        return next_date(
            rule=rule, month=month, day=day, every_years=every, anchor_year=anchor, since=TODAY
        )

    assert upcoming(CycleRule.EVERY_N_YEARS, 1, 20, every=3) == date(2029, 1, 20)
    assert upcoming(CycleRule.EVERY_N_YEARS, 3, 1, every=3, anchor=2030) == date(2030, 3, 1)
    assert upcoming(CycleRule.ANNUAL, 2, 29) == date(2028, 2, 29)
    # 29 февраля раз в три года с 2026-го: 2026, 2029, 2032 — високосный первым будет 2032.
    assert upcoming(CycleRule.EVERY_N_YEARS, 2, 29, every=3) == date(2032, 2, 29)
    assert upcoming(CycleRule.ANNUAL, 2, 30) is None


def test_next_date_counts_steps_from_anchor_year() -> None:
    def upcoming(month: int, day: int, every: int, anchor: int):
        return next_date(
            rule=CycleRule.EVERY_N_YEARS,
            month=month,
            day=day,
            every_years=every,
            anchor_year=anchor,
            since=TODAY,
        )

    # Начало через десять лет — предел формы: день существует, просто нескоро.
    assert upcoming(1, 20, every=2, anchor=2036) == date(2036, 1, 20)
    # 29 февраля раз в три года с 2035-го: 2035, 2038, 2041 не високосные — первым будет 2044.
    assert upcoming(2, 29, every=3, anchor=2035) == date(2044, 2, 29)
    assert upcoming(2, 29, every=5, anchor=2033) == date(2048, 2, 29)
