/**
 * Данные раздела «Проекты» и действия над ними.
 *
 * Устроено так же, как будет с API: запросы и мутации TanStack Query, после записи
 * перечитываются и проекты, и Пульт — у них общие числа (инвариант 2). «Что если» — тоже
 * мутация, но ничего не перечитывает: она ничего не записала.
 *
 * Сейчас сервер — `demoProjects`. Когда появится API, меняются тела функций ниже.
 */

import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { demoProjects } from './demo';
import type { NewProject, ProjectStatus, WhatIfChange } from './model';

export function projectsQuery() {
  return queryOptions({
    queryKey: ['projects'],
    queryFn: async () => demoProjects.view(),
  });
}

export function projectQuery(id: string) {
  return queryOptions({
    queryKey: ['projects', id],
    queryFn: async () => demoProjects.detail(id),
  });
}

export function useProjects() {
  return useQuery(projectsQuery());
}

export function useProject(id: string | null) {
  return useQuery({ ...projectQuery(id ?? ''), enabled: id !== null });
}

/** После записи: и список, и карточки, и Пульт — одни числа везде. */
function useRefresh() {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: ['projects'] }),
      client.invalidateQueries({ queryKey: ['pult'] }),
    ]);
}

export function useCreateProject() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async (input: NewProject) => demoProjects.create(input),
    onSuccess: refresh,
  });
}

export function useProjectStatus() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async (input: { id: string; status: ProjectStatus; reason: string | null }) =>
      demoProjects.setStatus(input.id, input.status, input.reason),
    onSuccess: refresh,
  });
}

export function useImpediment() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async (input: { id: string; text: string }) =>
      demoProjects.setImpediment(input.id, input.text),
    onSuccess: refresh,
  });
}

/** «Что если» — расчёт без записи. Результат живёт в мутации, а не в кеше данных. */
export function useWhatIf() {
  return useMutation({
    mutationFn: async (input: { id: string; changes: WhatIfChange[] }) =>
      demoProjects.whatIf(input.id, input.changes),
  });
}

export function useApplyWhatIf() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async (input: { id: string; changes: WhatIfChange[] }) =>
      demoProjects.apply(input.id, input.changes),
    onSuccess: refresh,
  });
}
