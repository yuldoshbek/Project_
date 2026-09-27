/**
 * Данные раздела «Программы».
 *
 * Раздел только читает: программы правят в карточке проекта. После правки проекта или
 * задачи `useProjects` и `useTasks` перечитывают и `['programs']` — у них общие числа
 * (инвариант 2).
 *
 * Сейчас сервер — `demoPrograms`. Когда появится API, меняется тело `queryFn`.
 */

import { queryOptions, useQuery } from '@tanstack/react-query';

import { demoPrograms } from './demo';

export function programsQuery() {
  return queryOptions({ queryKey: ['programs'], queryFn: async () => demoPrograms.view() });
}

export function usePrograms() {
  return useQuery(programsQuery());
}
