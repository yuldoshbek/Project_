/**
 * Слова уведомлений — теми ключами и тем переводчиком, что собирает service worker.
 *
 * Переводчик `workerT()` — ровно тот, что в `src/sw.ts`: проверяется и то, что он готов сразу,
 * без ожидания, — пуш показывается в том же обработчике, куда пришёл.
 */

import { describe, expect, it } from 'vitest';

import type { LockScreen, PushRow } from './model';
import { notificationOf, summaryLines, workerT } from './push';

const t = workerT();

function pushRow(overrides: Partial<PushRow>): PushRow {
  return {
    title: 'Согласование ТЗ',
    section: 'milestones',
    decision_kind: null,
    context: null,
    deviation: 6,
    ...overrides,
  };
}

const LOCK: LockScreen = {
  awaiting: { count: 2, oldest: pushRow({}) },
  due: { count: 1, first: pushRow({ title: 'Выгрузка данных в субплатформу', deviation: 0 }) },
};

describe('утренняя сводка', () => {
  it('два пункта: что ждёт дольше всех и первый срок', () => {
    expect(notificationOf(t, { kind: 'summary', tag: 'x', url: '/', lock_screen: LOCK })).toEqual({
      title: 'Утренняя сводка',
      body:
        'Ждут решения: 2, дольше всех — «Согласование ТЗ», 6 дн.\n' +
        'Срок сегодня: «Выгрузка данных в субплатформу».',
    });
  });

  it('спросили сегодня — без «0 дн»; сроков несколько — первый и сколько ещё', () => {
    expect(
      summaryLines(t, {
        awaiting: { count: 1, oldest: pushRow({ deviation: 0 }) },
        due: { count: 3, first: pushRow({ title: 'Справка к совещанию', deviation: 0 }) },
      }),
    ).toEqual([
      'Ждут решения: 1 — «Согласование ТЗ», спросили сегодня.',
      'Срок сегодня: 3 — «Справка к совещанию» и ещё 2.',
    ]);
  });

  it('пустой пункт — фраза, а не нуль', () => {
    expect(summaryLines(t, { awaiting: null, due: null })).toEqual([
      'Решений не ждёт.',
      'Сроков сегодня нет.',
    ]);
  });

  it('решение без текста названо видом и объектом, без объекта — видом', () => {
    const untitled = pushRow({ title: null, section: 'decisions', decision_kind: 'hurry' });
    expect(
      summaryLines(t, {
        awaiting: null,
        due: { count: 1, first: { ...untitled, context: 'Справка для Кабмина' } },
      })[1],
    ).toBe('Срок сегодня: «Поторопить: „Справка для Кабмина“».');
    expect(summaryLines(t, { awaiting: null, due: { count: 1, first: untitled } })[1]).toBe(
      'Срок сегодня: «Поторопить».',
    );
  });

  it('удалённая запись без названия — её раздел, а не пустое место', () => {
    const deleted = pushRow({ title: null, section: 'tasks' });
    expect(summaryLines(t, { awaiting: { count: 1, oldest: deleted }, due: null })[0]).toBe(
      'Ждут решения: 1, дольше всех — «Задача», 6 дн.',
    );
  });
});

describe('вопрос помощника', () => {
  it('«Ждёт вашего решения» — объект и сам вопрос', () => {
    expect(
      notificationOf(t, {
        kind: 'question',
        tag: 'question:q-1',
        url: '/?view=summary',
        title: 'Согласование ТЗ',
        question: 'Утвердить перенос вехи?',
      }),
    ).toEqual({
      title: 'Ждёт вашего решения',
      body: '«Согласование ТЗ»: Утвердить перенос вехи?',
    });
  });

  it('объекта без названия — только вопрос, без пустых кавычек', () => {
    expect(
      notificationOf(t, {
        kind: 'question',
        tag: 'question:q-2',
        url: '/?view=summary',
        title: null,
        question: 'Утвердить перенос вехи?',
      }),
    ).toEqual({ title: 'Ждёт вашего решения', body: 'Утвердить перенос вехи?' });
  });
});

describe('данные не разобрались', () => {
  it('уведомление всё равно показывается: молчаливый пуш iOS наказывает отзывом подписки', () => {
    expect(notificationOf(t, null)).toEqual({
      title: 'ORBITA',
      body: 'Новое уведомление — откройте «Сводку» на Пульте.',
    });
  });
});
