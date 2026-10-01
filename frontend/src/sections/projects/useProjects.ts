/**
 * Данные раздела «Проекты» и действия над ними — `/api/v1/projects…`.
 *
 * После записи перечитываются и проекты, и Пульт: у них общие числа (инвариант 2), и
 * экран их не пересчитывает сам. Перечитываются и после отказа: отказ по версии значит,
 * что на экране устаревшая картина, и правку надо делать по свежей (инвариант 15).
 *
 * «Что если» — тоже мутация, но ничего не перечитывает: он ничего не записал.
 */

import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { request } from '@/shared/api/client';

import type {
  DatesChange,
  NewOrganization,
  NewProject,
  OrganizationRef,
  OrganizationRole,
  ProjectDetails,
  ProjectDetail,
  ProjectStatus,
  ProjectsView,
  WhatIfChange,
  WhatIfResult,
} from './model';

const BASE = '/api/v1/projects';

export function projectsQuery() {
  return queryOptions({
    queryKey: ['projects'],
    queryFn: () => request<ProjectsView>(BASE),
  });
}

export function projectQuery(id: string) {
  return queryOptions({
    queryKey: ['projects', id],
    queryFn: () => request<ProjectDetail>(`${BASE}/${id}`),
  });
}

/** Организации для выбора в карточке. Справочник меняется редко — без опроса. */
export function organizationsQuery() {
  return queryOptions({
    queryKey: ['organizations'],
    queryFn: () => request<OrganizationRef[]>('/api/v1/organizations'),
    staleTime: 5 * 60_000,
    refetchInterval: false,
  });
}

export function useOrganizations(enabled: boolean) {
  return useQuery({ ...organizationsQuery(), enabled });
}

export function useProjects() {
  return useQuery(projectsQuery());
}

export function useProject(id: string | null) {
  return useQuery({ ...projectQuery(id ?? ''), enabled: id !== null });
}

/**
 * После записи: и список, и карточки, и Пульт, и «Программы», и «Календарь» — одни числа
 * везде: программа — тот же проект, её срок, вехи и готовность правятся здесь, а срок и
 * вехи стоят в календаре со ступенью Пульта.
 */
function useRefresh() {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: ['projects'] }),
      client.invalidateQueries({ queryKey: ['pult'] }),
      client.invalidateQueries({ queryKey: ['programs'] }),
      client.invalidateQueries({ queryKey: ['calendar'] }),
    ]);
}

export function useCreateProject() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (input: NewProject) =>
      request<ProjectDetail>(BASE, { method: 'POST', body: input }),
    onSettled: refresh,
  });
}

export function useProjectStatus() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (input: {
      id: string;
      status: ProjectStatus;
      reason: string | null;
      version: number;
    }) =>
      request<void>(`${BASE}/${input.id}/status`, {
        method: 'PUT',
        body: { status: input.status, reason: input.reason, version: input.version },
      }),
    onSettled: refresh,
  });
}

export function useImpediment() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (input: { id: string; text: string; version: number }) =>
      request<void>(`${BASE}/${input.id}/impediment`, {
        method: 'PUT',
        body: { text: input.text, version: input.version },
      }),
    onSettled: refresh,
  });
}

/** «Что если» — расчёт без записи. Результат живёт в мутации, а не в кеше данных. */
export function useWhatIf() {
  return useMutation({
    mutationFn: (input: { id: string; changes: WhatIfChange[] }) =>
      request<WhatIfResult>(`${BASE}/${input.id}/what-if`, {
        method: 'POST',
        body: { changes: input.changes },
      }),
  });
}

export function useApplyWhatIf() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (input: { id: string; changes: DatesChange[] }) =>
      request<void>(`${BASE}/${input.id}/dates`, {
        method: 'PUT',
        body: { changes: input.changes },
      }),
    onSettled: refresh,
  });
}

/** Сведения проекта: название, ответственный, направление, регион, описание. */
export function useSaveDetails() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (input: { id: string; details: ProjectDetails }) =>
      request<void>(`${BASE}/${input.id}/details`, { method: 'PUT', body: input.details }),
    onSettled: refresh,
  });
}

/**
 * Добавить организацию в проект или сменить её роль. `version: null` — добавление:
 * организации в проекте ещё нет.
 */
export function useSetOrganization() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (input: {
      projectId: string;
      organizationId: string;
      role: OrganizationRole;
      version: number | null;
    }) =>
      request<void>(`${BASE}/${input.projectId}/organizations/${input.organizationId}`, {
        method: 'PUT',
        body: { role: input.role, version: input.version },
      }),
    onSettled: refresh,
  });
}

export function useRemoveOrganization() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (input: { projectId: string; organizationId: string; version: number }) =>
      request<void>(`${BASE}/${input.projectId}/organizations/${input.organizationId}`, {
        method: 'DELETE',
        query: { version: input.version },
      }),
    onSettled: refresh,
  });
}

/** Новая организация — название и вид; сразу доступна для выбора. */
export function useCreateOrganization() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: NewOrganization) =>
      request<OrganizationRef>('/api/v1/organizations', { method: 'POST', body: input }),
    onSettled: () => client.invalidateQueries({ queryKey: ['organizations'] }),
  });
}
