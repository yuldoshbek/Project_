/**
 * Что и как часто обновляется.
 *
 * Опрос, а не постоянное соединение (ADR-0034). Цена у данных разная, поэтому и частота:
 *
 * - **метка изменений** — раз в 15 секунд и сразу при возврате на вкладку (`changes.ts`):
 *   один лёгкий ответ вместо данных. Данные разделов сами не опрашиваются (умолчание
 *   `QUERY_DEFAULTS`) — их перечитывает смена метки. Раньше Пульт собирался целиком раз в
 *   15 секунд, даже когда за день не менялось ничего (HANDOFF, «Известные ограничения»);
 * - **кто вошёл** (`/api/me`) — раз в минуту: перевыпуск ссылки гасит сессию, и экран
 *   «откройте по ссылке» должен появиться без перезагрузки;
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

import { queryOptions, skipToken } from '@tanstack/react-query';

import { ApiError } from './client';
import { api, type AccessLink, type Role } from './orbita';

/** Метка изменений: 15 секунд — компромисс из ADR-0034. */
export const POLL_INTERVAL_MS = 15_000;

/** Кто вошёл: перевыпуск ссылки виден не позже чем через минуту. */
export const ME_INTERVAL_MS = 60_000;

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

/**
 * Умолчания клиента запросов: всё, что не сказало иного, — данные разделов. Сами они не
 * опрашиваются и не устаревают: свежесть держит метка изменений (`useChangeStamp`), а после
 * своей правки экран перечитывает затронутое сам.
 */
export const QUERY_DEFAULTS = {
  refetchInterval: false as const,
  refetchOnWindowFocus: false,
  staleTime: Infinity,
  retry: retryUpTo(1),
};

export function currentUserQuery() {
  return queryOptions({
    queryKey: ['me'],
    queryFn: api.me,
    retry: retryUpTo(2),
    refetchInterval: pollEvery(ME_INTERVAL_MS),
    refetchOnWindowFocus: true,
    staleTime: ME_INTERVAL_MS,
  });
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

/**
 * Только что перевыпущенная ссылка роли. Не запрашивается — её кладёт перевыпуск. Показывается
 * один раз, но не пропадает ни со сменой вкладки, ни вместе с оболочкой, когда своя ссылка
 * гасит сессию того, кто нажал: тогда её показывает экран «откройте по ссылке» (`App`).
 * Токена в базе нет, только отпечаток, — второй раз ту же ссылку не получить.
 */
export function issuedLinkQuery(role: Role) {
  return queryOptions<AccessLink>({
    queryKey: ['issued-link', role],
    queryFn: skipToken,
    staleTime: Infinity,
    gcTime: Infinity,
  });
}
