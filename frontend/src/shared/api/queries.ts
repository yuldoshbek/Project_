/**
 * Что и как часто обновляется.
 *
 * Опрос, а не постоянное соединение (ADR-0034). Цена у данных разная, поэтому и частота:
 *
 * - **данные разделов** — раз в 15 секунд и сразу при возврате на вкладку: это умолчание
 *   клиента запросов, `QUERY_DEFAULTS`;
 * - **состояние системы** — раз в минуту: коммит и контур меняются только при выкладке;
 * - **справочники** — не опрашиваются: состав меняется редко, а опрос раз в 15 секунд
 *   тянул бы его целиком ради ответа «ничего не изменилось».
 *
 * Отказ 401 или 403 не опрашивается и не повторяется: повтор не создаст сессию и не сменит
 * роль, а мигание «загрузка — отказ — загрузка» выглядит как поломка.
 *
 * Параметры одного вида данных собраны в одну функцию-опцию (`healthQuery` и соседние).
 * Две подписки на один ключ с разными параметрами — это опрос с частотой той, что чаще:
 * так карточка «Состояние системы» спрашивала `/api/health` раз в 15 секунд вместо минуты.
 */

import { queryOptions } from '@tanstack/react-query';

import { ApiError } from './client';
import { api, type Role } from './orbita';

/** Данные разделов: 15 секунд — компромисс из ADR-0034. */
export const POLL_INTERVAL_MS = 15_000;

/** Состояние системы меняется только при выкладке. */
export const HEALTH_INTERVAL_MS = 60_000;

function isRefusal(error: unknown): boolean {
  return error instanceof ApiError && error.refusal;
}

/** Интервал опроса, который останавливается на отказе 401/403. */
export function pollEvery(ms: number) {
  return (query: { state: { error: unknown } }): number | false =>
    isRefusal(query.state.error) ? false : ms;
}

/** Сколько раз повторить упавший запрос. Отказ 401/403 не повторяется ни разу. */
export function retryUpTo(times: number) {
  return (failureCount: number, error: unknown): boolean =>
    !isRefusal(error) && failureCount < times;
}

/** Умолчания клиента запросов: всё, что не сказало иного, — данные разделов. */
export const QUERY_DEFAULTS = {
  refetchInterval: pollEvery(POLL_INTERVAL_MS),
  refetchOnWindowFocus: true,
  staleTime: POLL_INTERVAL_MS,
  retry: retryUpTo(1),
};

export function currentUserQuery() {
  return queryOptions({ queryKey: ['me'], queryFn: api.me, retry: retryUpTo(2) });
}

export function healthQuery() {
  return queryOptions({
    queryKey: ['health'],
    queryFn: api.health,
    refetchInterval: pollEvery(HEALTH_INTERVAL_MS),
    staleTime: HEALTH_INTERVAL_MS,
  });
}

export function dictionariesQuery() {
  return queryOptions({
    queryKey: ['dictionaries'],
    queryFn: api.dictionaries,
    staleTime: Infinity,
    refetchInterval: false,
  });
}

export function sessionsQuery(role: Role) {
  return queryOptions({ queryKey: ['sessions', role], queryFn: () => api.sessions(role) });
}
