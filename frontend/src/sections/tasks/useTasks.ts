/**
 * Данные раздела «Задачи» и действия над ними — `/api/v1/tasks…`.
 *
 * После записи перечитываются задачи, Пульт, проекты и программы — у них общие числа
 * (инвариант 2): закрытая задача меняет готовность проекта и программы и строку лестницы. Перечитываются и после
 * отказа: отказ по версии значит, что картина на экране устарела (инвариант 15).
 *
 * Разбор строки — мутация без записи и без перечитывания: он ничего не меняет.
 */

import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { request } from '@/shared/api/client';

import type { NewTask, ParsedLine, TaskDetail, TaskEdit, TaskStatus, TasksView } from './model';

const BASE = '/api/v1/tasks';

export function tasksQuery() {
  return queryOptions({ queryKey: ['tasks'], queryFn: () => request<TasksView>(BASE) });
}

export function taskQuery(id: string) {
  return queryOptions({
    queryKey: ['tasks', id],
    queryFn: () => request<TaskDetail>(`${BASE}/${id}`),
  });
}

export function useTasks() {
  return useQuery(tasksQuery());
}

export function useTask(id: string | null) {
  return useQuery({ ...taskQuery(id ?? ''), enabled: id !== null });
}

function useRefresh() {
  const client = useQueryClient();
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: ['tasks'] }),
      client.invalidateQueries({ queryKey: ['pult'] }),
      client.invalidateQueries({ queryKey: ['projects'] }),
      client.invalidateQueries({ queryKey: ['programs'] }),
    ]);
}

/** Разбор строки: что поняли — тип, срок, ответственный. Ничего не записывает. */
export function useParse() {
  return useMutation({
    mutationFn: (text: string) =>
      request<ParsedLine>(`${BASE}/parse`, { method: 'POST', body: { text } }),
  });
}

export function useCreateTask() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (input: NewTask) => request<TaskDetail>(BASE, { method: 'POST', body: input }),
    onSettled: refresh,
  });
}

export function useTaskStatus() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (input: { id: string; status: TaskStatus; version: number }) =>
      request<void>(`${BASE}/${input.id}/status`, {
        method: 'PUT',
        body: { status: input.status, version: input.version },
      }),
    onSettled: refresh,
  });
}

export function useEditTask() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (input: { id: string; edit: TaskEdit }) =>
      request<void>(`${BASE}/${input.id}`, { method: 'PUT', body: input.edit }),
    onSettled: refresh,
  });
}

export type ChecklistAction =
  | { kind: 'add'; id: string; text: string }
  | { kind: 'toggle'; id: string; itemId: string; done: boolean; version: number }
  | { kind: 'remove'; id: string; itemId: string; version: number };

async function perform(action: ChecklistAction): Promise<void> {
  const base = `${BASE}/${action.id}/checklist`;
  switch (action.kind) {
    case 'add':
      await request(base, { method: 'POST', body: { text: action.text } });
      return;
    case 'toggle':
      await request(`${base}/${action.itemId}`, {
        method: 'PUT',
        body: { is_done: action.done, version: action.version },
      });
      return;
    case 'remove':
      await request(`${base}/${action.itemId}`, {
        method: 'DELETE',
        query: { version: action.version },
      });
  }
}

export function useChecklist() {
  const refresh = useRefresh();
  return useMutation({ mutationFn: perform, onSettled: refresh });
}
