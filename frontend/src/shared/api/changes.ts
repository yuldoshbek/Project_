/**
 * Опрос по метке изменений (ADR-0034).
 *
 * Раз в 15 секунд и при возврате на вкладку экран спрашивает одну строку — метку
 * (`GET /api/v1/changes`). Совпала с прошлой — не делается ничего. Сменилась — данные
 * разделов помечаются устаревшими: те, что на экране, перечитываются сразу, остальные — при
 * переходе к ним. Правка второго пользователя видна так же быстро, как при прежнем опросе
 * данных, а запрос без изменений стоит один лёгкий ответ, а не сборку Пульта целиком.
 *
 * При скрытой вкладке опрос стоит (так ведёт себя клиент запросов по умолчанию): телефон
 * в кармане не будит ни себя, ни базу.
 */

import { queryOptions, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';

import { request } from './client';
import { POLL_INTERVAL_MS, pollEvery, retryUpTo } from './queries';

/** Чего смена метки не касается: у них своя частота, или это не данные разделов. */
const OWN_CADENCE = new Set(['changes', 'me', 'health', 'file-link', 'search', 'issued-link']);

export function changesQuery() {
  return queryOptions({
    queryKey: ['changes'],
    queryFn: () => request<{ stamp: string }>('/api/v1/changes'),
    refetchInterval: pollEvery(POLL_INTERVAL_MS),
    refetchOnWindowFocus: true,
    staleTime: 0,
    retry: retryUpTo(1),
  });
}

export function useChangeStamp(enabled: boolean): void {
  const client = useQueryClient();
  const stamp = useQuery({ ...changesQuery(), enabled }).data?.stamp;
  const seen = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!stamp) return;
    const previous = seen.current;
    seen.current = stamp;
    if (previous === undefined || previous === stamp) return;
    void client.invalidateQueries({
      predicate: (query) => !OWN_CADENCE.has(String(query.queryKey[0])),
    });
  }, [client, stamp]);
}
