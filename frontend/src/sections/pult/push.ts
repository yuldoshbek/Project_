/**
 * Слова уведомлений: утренняя сводка и «ждёт вашего решения».
 *
 * Одни и те же функции складывают текст и в предпросмотре на вкладке «Сводка», и в service
 * worker, который показывает пришедший пуш (`src/sw.ts`): сервер шлёт данные, а не текст
 * (ADR-0036).
 *
 * Поэтому модуль не импортирует ничего из приложения, кроме типов и словаря: worker собирается
 * отдельно, и в нём нет ни React, ни экземпляра i18next приложения. `rowTitle` живёт здесь же —
 * на ней стоит название в уведомлении; экранам её отдаёт `text.ts`.
 */

import { createInstance, type TFunction } from 'i18next';

import { ru } from '@/shared/i18n/ru';

import type { DecisionKind, LockScreen, PushPayload, PushRow, RowSection } from './model';

/** Куда ведёт касание уведомления: вкладка «Сводка» Пульта. */
export const SUMMARY_URL = '/?view=summary';

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

/**
 * Название в тексте уведомления. У решения без текста на Пульте рядом видна строка объекта, а
 * на экране блокировки её нет: одно «Поторопить» не скажет, о какой работе речь.
 */
function pushTitle(t: TFunction, row: PushRow): string {
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
export function summaryLines(t: TFunction, lock: LockScreen): string[] {
  const { awaiting, due } = lock;

  const waiting = !awaiting
    ? t('pult.summary.push.noAwaiting')
    : awaiting.oldest.deviation === 0
      ? t('pult.summary.push.awaitingToday', {
          count: awaiting.count,
          title: pushTitle(t, awaiting.oldest),
        })
      : t('pult.summary.push.awaiting', {
          count: awaiting.count,
          title: pushTitle(t, awaiting.oldest),
          days: awaiting.oldest.deviation,
        });
  const today = !due
    ? t('pult.summary.push.noDue')
    : due.count === 1
      ? t('pult.summary.push.dueOne', { title: pushTitle(t, due.first) })
      : t('pult.summary.push.dueMany', {
          count: due.count,
          title: pushTitle(t, due.first),
          more: due.count - 1,
        });
  return [waiting, today];
}

export interface NotificationText {
  title: string;
  body: string;
}

/**
 * Заголовок и текст уведомления из данных пуша.
 *
 * `null` — данные не разобрались (например, сервер уже новее закешированного worker).
 * Уведомление показывается и тогда: iOS отзывает подписку у приложения, которое получает пуши
 * и ничего не показывает, — после этого сводка перестала бы приходить совсем.
 */
export function notificationOf(t: TFunction, payload: PushPayload | null): NotificationText {
  switch (payload?.kind) {
    case 'summary':
      return {
        title: t('pult.summary.push.title'),
        body: summaryLines(t, payload.lock_screen).join('\n'),
      };
    case 'question':
      return {
        title: t('pult.summary.push.questionTitle'),
        // Без названия объекта — только вопрос: ««»: …» читалось бы как поломка.
        body: payload.title
          ? t('pult.summary.push.question', { title: payload.title, question: payload.question })
          : payload.question,
      };
    default:
      return { title: t('app.name'), body: t('pult.summary.push.unreadable') };
  }
}

/**
 * Переводчик для service worker: свой экземпляр i18next, готовый сразу, без ожидания. Пуш
 * приходит в обработчик события, и слова нужны в нём же, а экземпляр приложения держит
 * react-i18next, которого в worker нет.
 */
export function workerT(): TFunction {
  const i18n = createInstance();
  void i18n.init({
    resources: { ru: { translation: ru } },
    lng: 'ru',
    fallbackLng: 'ru',
    // Словарь лежит в сборке, грузить нечего: `t` работает сразу после `init`.
    initAsync: false,
    interpolation: { escapeValue: false },
    // Пропущенный ключ виден, как и в приложении (`shared/i18n`), а не пустое место.
    parseMissingKeyHandler: (key) => `⟨${key}⟩`,
    showSupportNotice: false,
  });
  return i18n.t;
}
