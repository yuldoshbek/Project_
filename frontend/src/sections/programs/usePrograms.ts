/**
 * Данные раздела «Программы» — `GET /api/v1/programs`.
 *
 * Раздел только читает: программы правят в карточке проекта. После правки проекта или
 * задачи `useProjects` и `useTasks` перечитывают и `['programs']` — у них общие числа
 * (инвариант 2).
 */

import { queryOptions, useQuery } from '@tanstack/react-query';

import { request } from '@/shared/api/client';

import type { ProgramsView } from './model';

export function programsQuery() {
  return queryOptions({
    queryKey: ['programs'],
    queryFn: () => request<ProgramsView>('/api/v1/programs'),
  });
}

export function usePrograms() {
  return useQuery(programsQuery());
}
