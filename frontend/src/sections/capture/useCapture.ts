/**
 * Данные Захвата — `/api/v1/captures`.
 *
 * После записи перечитываются недавние, и после отказа тоже. Если запись ушла в «Задачи», —
 * и всё, где задача видна: «Задачи», Пульт, проекты, программы, календарь (инвариант 2).
 * Отказ задачу не заводит: запись и задача — одна транзакция сервера.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { request } from '@/shared/api/client';

import type { CaptureView, NewCapture, SavedCapture } from './model';

const BASE = '/api/v1/captures';

const WITH_TASKS = [['tasks'], ['pult'], ['projects'], ['programs'], ['calendar']];

export function useCaptures() {
  return useQuery({ queryKey: ['captures'], queryFn: () => request<CaptureView>(BASE) });
}

export function useSaveCapture() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (input: NewCapture) => request<SavedCapture>(BASE, { method: 'POST', body: input }),
    onSettled: (saved) =>
      Promise.all([
        client.invalidateQueries({ queryKey: ['captures'] }),
        ...(saved?.destination === 'tasks'
          ? WITH_TASKS.map((queryKey) => client.invalidateQueries({ queryKey }))
          : []),
      ]),
  });
}
