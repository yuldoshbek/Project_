/**
 * Данные раздела «Задачи» и действия над ними.
 *
 * Устроено так же, как будет с API: запросы и мутации TanStack Query, после записи
 * перечитываются и задачи, и Пульт, и проекты — у них общие числа (инвариант 2): закрытая
 * задача меняет готовность проекта и строку лестницы. Разбор строки — мутация без записи.
 *
 * Сейчас сервер — `demoTasks`. Когда появится API, меняются тела функций ниже.
 */

import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { demoTasks } from './demo';
import type { NewTask, TaskEdit, TaskStatus } from './model';

export function tasksQuery() {
  return queryOptions({ queryKey: ['tasks'], queryFn: async () => demoTasks.view() });
}

export function taskQuery(id: string) {
  return queryOptions({ queryKey: ['tasks', id], queryFn: async () => demoTasks.detail(id) });
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
    ]);
}

/** Разбор строки: что поняли — тип, срок, ответственный. Ничего не записывает. */
export function useParse() {
  return useMutation({ mutationFn: async (text: string) => demoTasks.parse(text) });
}

export function useCreateTask() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async (input: NewTask) => demoTasks.create(input),
    onSettled: refresh,
  });
}

export function useTaskStatus() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async (input: { id: string; status: TaskStatus; version: number }) =>
      demoTasks.setStatus(input.id, input.status, input.version),
    onSettled: refresh,
  });
}

export function useEditTask() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async (input: { id: string; edit: TaskEdit }) =>
      demoTasks.edit(input.id, input.edit),
    onSettled: refresh,
  });
}

export function useChecklist() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async (
      input:
        | { kind: 'add'; id: string; text: string }
        | { kind: 'toggle'; id: string; itemId: string; done: boolean }
        | { kind: 'remove'; id: string; itemId: string },
    ) => {
      if (input.kind === 'add') demoTasks.addItem(input.id, input.text);
      else if (input.kind === 'toggle') demoTasks.toggleItem(input.id, input.itemId, input.done);
      else demoTasks.removeItem(input.id, input.itemId);
    },
    onSettled: refresh,
  });
}
