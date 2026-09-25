/**
 * Подписи строки Пульта: отклонение словами ступени и срок.
 *
 * Отдельно от компонентов, потому что нужны и строке, и средней панели монитора, и тестам.
 */

import type { TFunction } from 'i18next';

import { formatDate } from '@/shared/time';

import type { PultRow } from './model';

/** «Ждёт 6 дн», «срок завтра», «тишина 21 дн» — число рядом со ступенью, словами ступени. */
export function deviationText(t: TFunction, row: PultRow): string {
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
