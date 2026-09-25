/**
 * Частота опроса и повторы.
 *
 * Ошибка здесь не видна на экране, а видна в счёте за сеть и в мигании: отказ 401,
 * опрашиваемый раз в 15 секунд, или справочники, которые тянутся заново каждые 15 секунд.
 */

import { describe, expect, it } from 'vitest';

import { ApiError } from './client';
import {
  dictionariesQuery,
  HEALTH_INTERVAL_MS,
  healthQuery,
  POLL_INTERVAL_MS,
  pollEvery,
  retryUpTo,
} from './queries';

function after(error: unknown) {
  return { state: { error } };
}

describe('опрос', () => {
  it('идёт с заданной частотой, пока запрос отвечает или падает по сети', () => {
    const interval = pollEvery(POLL_INTERVAL_MS);
    expect(interval(after(null))).toBe(POLL_INTERVAL_MS);
    expect(interval(after(new ApiError(500, 'сбой')))).toBe(POLL_INTERVAL_MS);
    expect(interval(after(new TypeError('сеть')))).toBe(POLL_INTERVAL_MS);
  });

  it('останавливается на отказе 401 и 403', () => {
    const interval = pollEvery(POLL_INTERVAL_MS);
    expect(interval(after(new ApiError(401, 'нет сессии')))).toBe(false);
    expect(interval(after(new ApiError(403, 'только помощник')))).toBe(false);
  });

  it('справочники не опрашиваются и не устаревают', () => {
    const options = dictionariesQuery();
    expect(options.staleTime).toBe(Infinity);
    expect(options.refetchInterval).toBe(false);
  });

  it('состояние системы — раз в минуту', () => {
    const { refetchInterval } = healthQuery();
    expect(typeof refetchInterval).toBe('function');
    if (typeof refetchInterval !== 'function') return;
    expect(HEALTH_INTERVAL_MS).toBe(60_000);
    expect(refetchInterval(after(null) as never)).toBe(HEALTH_INTERVAL_MS);
  });
});

describe('повтор упавшего запроса', () => {
  it('сбой повторяется до предела', () => {
    const retry = retryUpTo(1);
    expect(retry(0, new ApiError(500, 'сбой'))).toBe(true);
    expect(retry(1, new ApiError(500, 'сбой'))).toBe(false);
  });

  it('отказ 401 и 403 не повторяется ни разу', () => {
    const retry = retryUpTo(2);
    expect(retry(0, new ApiError(401, 'нет сессии'))).toBe(false);
    expect(retry(0, new ApiError(403, 'только помощник'))).toBe(false);
  });
});
