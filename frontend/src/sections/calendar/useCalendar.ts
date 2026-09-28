/**
 * Данные раздела «Календарь» и действия с годовыми циклами.
 *
 * Устроено так же, как будет с API: запросы и мутации TanStack Query; после записи цикла
 * перечитывается весь календарь. Даты будущего цикла до записи — запрос без записи, как
 * разбор строки у задач.
 *
 * Сейчас сервер — `demoCalendar`. Когда появится API, меняются тела функций ниже.
 */

import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { demoCalendar } from './demo';
import type { CycleRuleFields, NewCycle } from './model';

export function useCalendar(range: { from: string; to: string }) {
  return useQuery({
    queryKey: ['calendar', range.from, range.to],
    queryFn: async () => demoCalendar.view(range),
    // Листание месяцев не мигает пустым экраном: пока грузится следующий, виден прежний.
    placeholderData: keepPreviousData,
  });
}

/** Все действующие циклы — и те, у которых за год вперёд дат нет. */
export function useCycles() {
  return useQuery({
    queryKey: ['calendar', 'cycles'],
    queryFn: async () => demoCalendar.list(),
  });
}

export function useCycle(id: string) {
  return useQuery({
    queryKey: ['calendar', 'cycle', id],
    queryFn: async () => demoCalendar.cycle(id),
  });
}

/**
 * Даты будущего цикла до записи: помощник видит, что заводит. Ничего не записывает.
 *
 * Ключ — только правило: название, проект и ответственный на даты не влияют, и каждая
 * буква названия была бы новым запросом. Пока правило неполное (стёртое число), запроса
 * нет; пока считается новое, видны прежние даты, а не пустая строка.
 */
export function useCyclePreview(rule: CycleRuleFields | null) {
  return useQuery({
    queryKey: [
      'calendar',
      'preview',
      rule?.rule,
      rule?.month,
      rule?.day,
      rule?.every_years,
      rule?.anchor_year,
    ],
    queryFn: async () => demoCalendar.preview(rule!),
    enabled: rule !== null,
    placeholderData: keepPreviousData,
    refetchInterval: false,
  });
}

function useRefresh() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: ['calendar'] });
}

export function useCreateCycle() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async (input: NewCycle) => demoCalendar.create(input),
    onSettled: refresh,
  });
}

export function useCancelCycle() {
  const client = useQueryClient();
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async (input: { id: string; version: number }) =>
      demoCalendar.cancel(input.id, input.version),
    // Отменённого цикла больше нет: без этого перечитывание спросило бы и его — отказ,
    // повтор через секунду, и лист закрывался бы на секунду позже, после ошибки.
    onSuccess: (_, input) => {
      client.removeQueries({ queryKey: ['calendar', 'cycle', input.id], exact: true });
    },
    onSettled: refresh,
  });
}
