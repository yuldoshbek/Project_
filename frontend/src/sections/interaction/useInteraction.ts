/**
 * Данные раздела «Взаимодействие» и действия — `/api/v1/interaction…`.
 *
 * После каждой правки перечитываются раздел и Пульт: ответ на письмо меняет и строку, и
 * ответы вопросов, и скорость организации, и строку лестницы Пульта (инвариант 2).
 * Перечитываются и после отказа: отказ по версии значит, что картина устарела
 * (инвариант 15).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { request } from '@/shared/api/client';

import type { InteractionView, NewLetter, OrganizationCard, Rating } from './model';

const KEY = ['interaction'];
const BASE = '/api/v1/interaction';

export function useInteraction() {
  return useQuery({ queryKey: KEY, queryFn: () => request<InteractionView>(BASE) });
}

export function useOrganization(id: string) {
  return useQuery({
    queryKey: [...KEY, 'organization', id],
    queryFn: () => request<OrganizationCard>(`${BASE}/organizations/${id}`),
  });
}

function useChange<T, R = void>(perform: (input: T) => Promise<R>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: perform,
    onSettled: () =>
      Promise.all([KEY, ['pult']].map((queryKey) => client.invalidateQueries({ queryKey }))),
  });
}

/** Оценка ответа — руководитель, одно касание (ТЗ 3.4, 11). Повторное касание снимает её. */
export function useRate() {
  return useChange((input: { id: string; rating: Rating | null; version: number }) =>
    request<void>(`${BASE}/letters/${input.id}/rating`, {
      method: 'PUT',
      body: { rating: input.rating, version: input.version },
    }),
  );
}

export function useAnswer() {
  return useChange((input: { id: string; on: string; number: string | null; version: number }) =>
    request<void>(`${BASE}/letters/${input.id}/answer`, {
      method: 'PUT',
      body: { on: input.on, number: input.number, version: input.version },
    }),
  );
}

export function useAddLetter() {
  return useChange((input: NewLetter) =>
    request<{ id: string }>(`${BASE}/letters`, { method: 'POST', body: input }),
  );
}

export function useNextStep() {
  return useChange(
    (input: { id: string; next_step: string; next_step_on: string | null; version: number }) =>
      request<void>(`${BASE}/agreements/${input.id}/next-step`, {
        method: 'PUT',
        body: {
          next_step: input.next_step,
          next_step_on: input.next_step_on,
          version: input.version,
        },
      }),
  );
}
