/**
 * Подписи строки Пульта: отклонение словами ступени и срок.
 *
 * Отдельно от компонентов, потому что нужны и строке, и средней панели монитора, и тестам.
 */

import type { TFunction } from 'i18next';

import { formatDate } from '@/shared/time';

import type { DecisionKind, PultRow, RowSection, SummaryView } from './model';

/**
 * Название строки. У решения без текста названия нет — подписью служит вид решения, у
 * удалённой записи — её раздел: пустая строка на экране читается как «данных нет».
 */
export function rowTitle(
  t: TFunction,
  row: { title: string | null; section: RowSection; decision_kind?: DecisionKind | null },
): string {
  if (row.title) return row.title;
  if (row.decision_kind) return t(`pult.decisions.${row.decision_kind}`);
  return t(`pult.rowSections.${row.section}`);
}

/** «Ждёт 6 дн», «срок завтра», «тишина 21 дн» — число рядом со ступенью, словами ступени. */
export function deviationText(t: TFunction, row: Pick<PultRow, 'step' | 'deviation'>): string {
  const days = row.deviation;
  if (row.step === 'awaiting_decision') {
    return days === 0
      ? t('pult.deviation.awaitingToday')
      : t('pult.deviation.awaiting_decision', { days });
  }
  if (row.step === 'burning') {
    if (days === 0) return t('pult.deviation.burningToday');
    if (days === 1) return t('pult.deviation.burningTomorrow');
  }
  return t(`pult.deviation.${row.step}`, { days });
}

/** «Срок 25.09» или «Срок 12.09 → 25.09», если срок переносили. */
export function dueText(t: TFunction, row: PultRow): string | null {
  if (!row.due_on) return null;
  if (row.original_due_on && row.original_due_on !== row.due_on) {
    return t('pult.dueMoved', {
      from: formatDate(row.original_due_on),
      to: formatDate(row.due_on),
    });
  }
  return t('pult.due', { date: formatDate(row.due_on) });
}

/**
 * Название в тексте уведомления. У решения без текста на Пульте рядом видна строка объекта, а
 * на экране блокировки её нет: одно «Поторопить» не скажет, о какой работе речь.
 */
function pushTitle(t: TFunction, row: PultRow): string {
  if (!row.title && row.decision_kind && row.context) {
    return t('pult.summary.push.decision', {
      kind: t(`pult.decisions.${row.decision_kind}`),
      context: row.context,
    });
  }
  return rowTitle(t, row);
}

/**
 * Текст утренней сводки на экране блокировки (V29): числа и два названия — то, что ждёт
 * дольше всех, и первый срок. Больше экран блокировки не показывает, а длинный текст iPhone
 * обрежет сам, не спросив, что важнее.
 *
 * Пустой пункт — фраза, а не нуль (ТЗ 5): «0 ждут решения» читается как поломка. Оценки
 * «сегодня спокойно» нет: просроченное в сводку не входит (V26), и при нём «спокойно» было бы
 * неправдой.
 */
export function summaryLines(t: TFunction, summary: SummaryView): string[] {
  const [oldest] = summary.awaiting;
  const [first] = summary.due_today;

  const awaiting = !oldest
    ? t('pult.summary.push.noAwaiting')
    : oldest.deviation === 0
      ? t('pult.summary.push.awaitingToday', {
          count: summary.awaiting.length,
          title: pushTitle(t, oldest),
        })
      : t('pult.summary.push.awaiting', {
          count: summary.awaiting.length,
          title: pushTitle(t, oldest),
          days: oldest.deviation,
        });
  const due = !first
    ? t('pult.summary.push.noDue')
    : summary.due_today.length === 1
      ? t('pult.summary.push.dueOne', { title: pushTitle(t, first) })
      : t('pult.summary.push.dueMany', {
          count: summary.due_today.length,
          title: pushTitle(t, first),
          more: summary.due_today.length - 1,
        });
  return [awaiting, due];
}
