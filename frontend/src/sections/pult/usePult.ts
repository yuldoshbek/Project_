/**
 * Данные Пульта и три действия над ними: решить, спросить, отменить.
 *
 * Запрос — `GET /api/v1/pult`, опрос по умолчанию раз в 15 секунд (ADR-0034,
 * `shared/api/queries.ts`). После действия лестница перечитывается у сервера: экран не
 * пересчитывает счётчики сам (инвариант 2).
 *
 * Решение и вопрос возвращают идентификатор записи — его держит кнопка «Отменить»:
 * отмена — это удаление ровно того, что создано этим касанием, а не «последнего вообще».
 */

import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { request } from '@/shared/api/client';

import { deviceSetup, isAppleMobile, readEnvironment } from '@/app/notifications';
import { managementQuery } from '@/sections/management/useManagement';

import type { DecisionKind, PultView, ReportPeriod, ReportView, TargetType } from './model';
import { demoDevice, sendAtOf, summaryFrom } from './summary-demo';

export function pultQuery() {
  return queryOptions({
    queryKey: ['pult'],
    queryFn: () => request<PultView>('/api/v1/pult'),
  });
}

/** Отчёт недели или месяца. Не опрашивается: это документ на момент формирования. */
export function reportQuery(period: ReportPeriod, offset: number) {
  return queryOptions({
    queryKey: ['pult', 'report', period, offset],
    queryFn: () => request<ReportView>('/api/v1/pult/report', { query: { period, offset } }),
    refetchInterval: false,
    staleTime: 60_000,
  });
}

export function usePult() {
  return useQuery(pultQuery());
}

/**
 * Утренняя сводка. Пока — вымышленный сервер (`summary-demo.ts`): строки Пульта и время из
 * порога в ответе Управления. С API это станет `request('/api/v1/pult/summary')` под ключом
 * `['pult', 'summary']` — он перечитается после решения вместе с Пультом.
 *
 * Ключ не зависит от `as_of` Пульта: оно новое в каждом ответе, и под новым ключом вкладка
 * каждые 15 секунд уходила в «загрузку» — строка сворачивалась, черновик вопроса пропадал.
 */
export function useSummary(pult: PultView) {
  return useQuery({
    ...managementQuery(),
    select: (management) => summaryFrom(pult, sendAtOf(management)),
  });
}

const DEVICE_KEY = ['pult', 'device'];

/** Уведомления на этом устройстве: можно ли их включить и включены ли. */
export function useThisDevice() {
  const client = useQueryClient();
  const state = useQuery({
    queryKey: DEVICE_KEY,
    queryFn: async () => {
      const environment = readEnvironment();
      return {
        setup: deviceSetup(environment),
        apple: isAppleMobile(environment),
        enabledOn: demoDevice.enabled(),
      };
    },
    refetchInterval: false,
  });
  const enable = useMutation({
    mutationFn: async () => demoDevice.enable(),
    onSettled: () => client.invalidateQueries({ queryKey: DEVICE_KEY }),
  });
  return { state, enable };
}

export interface Target {
  target_type: TargetType;
  target_id: string;
}

export type PultAction =
  | { type: 'decide'; target: Target; kind: DecisionKind }
  | { type: 'ask'; target: Target; text: string }
  | { type: 'undo-decision'; id: string }
  | { type: 'undo-question'; id: string };

async function perform(action: PultAction): Promise<string | null> {
  switch (action.type) {
    case 'decide':
      return (
        await request<{ id: string }>('/api/v1/decisions', {
          method: 'POST',
          body: { ...action.target, kind: action.kind },
        })
      ).id;
    case 'ask':
      return (
        await request<{ id: string }>('/api/v1/questions', {
          method: 'POST',
          body: { ...action.target, text: action.text },
        })
      ).id;
    case 'undo-decision':
      await request(`/api/v1/decisions/${action.id}`, { method: 'DELETE' });
      return null;
    case 'undo-question':
      await request(`/api/v1/questions/${action.id}`, { method: 'DELETE' });
      return null;
  }
}

export function usePultAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: perform,
    // Решение со сроком встаёт в календарь, вопрос меняет ступень даты — те же числа.
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: pultQuery().queryKey }),
        client.invalidateQueries({ queryKey: ['calendar'] }),
      ]),
  });
}
