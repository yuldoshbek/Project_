/**
 * Подписи раздела: отсчёт до даты, срок вехи с переносом, «успеваем?» фразой.
 *
 * Общие для горизонта, плиток, «до конца года» и карточки программы — одна формулировка во
 * всех местах. Числа приходят с сервера; здесь только слова вокруг них.
 */

import type { TFunction } from 'i18next';

import { formatDate } from '@/shared/time';

import type { Pace, ProgramCard, ProgramMilestone, YearEndRow } from './model';

const count = new Intl.NumberFormat('ru-RU');

const monthYear = new Intl.DateTimeFormat('ru-RU', {
  month: '2-digit',
  year: 'numeric',
  timeZone: 'UTC',
});

const monthName = new Intl.DateTimeFormat('ru-RU', { month: 'long', timeZone: 'UTC' });

/** Дни с разрядами: «1 540», а не «1540» — длинный отсчёт читается с одного взгляда. */
export function formatCount(value: number): string {
  return count.format(value);
}

/** «Октябрь» — заголовок месяца в «до конца года». */
export function monthTitle(date: string): string {
  const name = monthName.format(new Date(`${date.slice(0, 7)}-01T00:00:00Z`));
  return name.charAt(0).toUpperCase() + name.slice(1);
}

/** Прогноз — с точностью до месяца: точный день у прогноза по темпу был бы неправдой. */
export function formatMonth(date: string): string {
  return monthYear.format(new Date(`${date.slice(0, 10)}T00:00:00Z`));
}

/** Отсчёт до даты программы: «осталось 591 дн», «дата сегодня», «дата прошла 3 дн назад». */
export function countdownText(t: TFunction, days: number): string {
  if (days > 0) return t('programs.countdown.left', { days: formatCount(days) });
  if (days === 0) return t('programs.countdown.today');
  return t('programs.countdown.past', { days: formatCount(-days) });
}

/** Сколько до вехи: «через 12 дн», «завтра», «просрочено 27 дн», «пройдена 22.09.2026». */
export function markLeftText(
  t: TFunction,
  mark: Pick<ProgramMilestone, 'days_left' | 'is_passed' | 'passed_on' | 'due_on'>,
): string {
  // Дату прохождения называем, только если она не совпала со сроком: рядом уже стоит срок,
  // и «22.09.2026 · пройдена 22.09.2026» — одно и то же дважды.
  if (mark.is_passed) {
    return mark.passed_on && mark.passed_on !== mark.due_on
      ? t('programs.mark.passedOn', { date: formatDate(mark.passed_on) })
      : t('programs.mark.passed');
  }
  if (mark.days_left > 1) return t('programs.mark.in', { days: formatCount(mark.days_left) });
  if (mark.days_left === 1) return t('programs.mark.tomorrow');
  if (mark.days_left === 0) return t('programs.mark.today');
  return t('programs.mark.overdue', { days: formatCount(-mark.days_left) });
}

/** Срок вехи: «30.09.2026» или «02.11.2026 → 16.11.2026», если переносили (ТЗ 11). */
export function markDateText(
  t: TFunction,
  mark: Pick<ProgramMilestone, 'due_on' | 'original_due_on'>,
): string {
  if (mark.original_due_on !== mark.due_on) {
    return t('programs.mark.moved', {
      from: formatDate(mark.original_due_on),
      to: formatDate(mark.due_on),
    });
  }
  return formatDate(mark.due_on);
}

/**
 * Разница прогноза и даты: месяцами, когда их набирается хотя бы два, иначе днями. Порог по
 * округлённым месяцам, а не по дням: иначе 45 дней читались бы как «≈ 1 мес», а 46 — уже
 * как «≈ 2 мес».
 */
export function gapText(t: TFunction, days: number): string {
  const size = Math.abs(days);
  const months = Math.round(size / 30.4);
  if (months >= 2) return t('programs.pace.months', { months });
  return t('programs.pace.days', { days: formatCount(size) });
}

/** «готово 14 % с подпроектами» — охват назван, раз у программы он шире своих вех. */
export function readinessText(
  t: TFunction,
  card: Pick<ProgramCard, 'readiness' | 'subprojects'>,
): string {
  return card.subprojects.length > 0
    ? t('programs.panel.readinessWithSubs', { value: card.readiness })
    : t('programs.panel.readiness', { value: card.readiness });
}

/**
 * «Успеваем?» фразой с правилом (ТЗ 5): что закрыто, что осталось, куда выводит темп.
 *
 * Правило названо в самой фразе, а не спрятано: руководитель должен видеть, из чего
 * вывод, — иначе «не успеваем» спорит с «готово 40 %», и не верят обоим.
 */
export function paceText(t: TFunction, pace: Pace, dueOn: string): string {
  if (pace.verdict === 'little_data') {
    return t('programs.pace.littleData', {
      window: pace.window_days,
      tasks: pace.closed_tasks,
      min: pace.min_closed_tasks,
    });
  }
  const values = {
    window: pace.window_days,
    closed: formatCount(pace.closed),
    remaining: formatCount(pace.remaining),
    forecast: pace.forecast_on ? formatMonth(pace.forecast_on) : '',
    due: formatDate(dueOn),
    gap: gapText(t, pace.gap_days ?? 0),
  };
  return pace.verdict === 'behind'
    ? t('programs.pace.behind', values)
    : t('programs.pace.onTrack', values);
}

/** Коротко — для строки программы в карточке «Успеваем?». */
export function paceShort(t: TFunction, pace: Pace): string {
  if (pace.verdict === 'little_data') return t('programs.pace.shortLittle');
  const gap = gapText(t, pace.gap_days ?? 0);
  return pace.verdict === 'behind'
    ? t('programs.pace.shortBehind', { gap })
    : t('programs.pace.shortOnTrack', { gap });
}

/** Хвост строки «до конца года» после отсчёта: « · 30.09.2026 · Каримов А.». */
export function metaText(t: TFunction, row: Pick<YearEndRow, 'milestone' | 'responsible'>): string {
  const parts = [markDateText(t, row.milestone), row.responsible?.name ?? null].filter(Boolean);
  return ` · ${parts.join(' · ')}`;
}
