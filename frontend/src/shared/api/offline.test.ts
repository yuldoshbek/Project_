/**
 * Последняя картина без сети: что хранится, сколько живёт и когда стирается.
 */

import { QueryClient } from '@tanstack/react-query';
import { afterEach, describe, expect, it } from 'vitest';

import { forgetLastPicture, keepLastPicture, restoreLastPicture } from './offline';
import { QUERY_DEFAULTS } from './queries';

const PULT = { as_of: '2026-10-09T05:00:00Z', rows: [] };

function client() {
  return new QueryClient({ defaultOptions: { queries: QUERY_DEFAULTS } });
}

async function answered(target: QueryClient, key: string[], data: unknown) {
  await target.fetchQuery({ queryKey: key, queryFn: () => Promise.resolve(data) });
}

afterEach(() => {
  window.localStorage.clear();
});

describe('последняя картина', () => {
  it('ответ Пульта хранится и при следующем открытии виден сразу — устаревшим', async () => {
    const first = client();
    const stop = keepLastPicture(first);
    await answered(first, ['pult'], PULT);
    stop();

    const next = client();
    restoreLastPicture(next);

    expect(next.getQueryData(['pult'])).toEqual(PULT);
    // Устаревшая: экран сразу спросит сервер, а не останется на прошлой картине.
    expect(next.getQueryState(['pult'])?.isInvalidated).toBe(true);
  });

  it('хранится только первый экран руководителя, а не все разделы', async () => {
    const first = client();
    const stop = keepLastPicture(first);
    await answered(first, ['ijro'], { items: ['поручение'] });
    stop();

    const next = client();
    restoreLastPicture(next);
    expect(next.getQueryData(['ijro'])).toBeUndefined();
  });

  it('картина старше недели не показывается', async () => {
    const first = client();
    const stop = keepLastPicture(first);
    await answered(first, ['pult'], PULT);
    stop();

    const next = client();
    restoreLastPicture(next, Date.now() + 8 * 24 * 60 * 60 * 1000);
    expect(next.getQueryData(['pult'])).toBeUndefined();
  });

  it('погашенная сессия стирает картину', async () => {
    const first = client();
    const stop = keepLastPicture(first);
    await answered(first, ['pult'], PULT);
    stop();

    forgetLastPicture();

    const next = client();
    restoreLastPicture(next);
    expect(next.getQueryData(['pult'])).toBeUndefined();
  });
});
