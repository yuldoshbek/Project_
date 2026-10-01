/**
 * Данные раздела «Взаимодействие».
 *
 * Сейчас сервер — `demoInteraction` (`demo.ts`). Когда появится API раздела, меняются тела
 * функций ниже, а экран — нет. После каждой правки раздел перечитывается целиком: ответ на
 * письмо меняет и строку, и ответы вопросов, и скорость организации.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { demoInteraction } from './demo';
import type { NewLetter, Rating } from './model';

const KEY = ['interaction'];

export function useInteraction() {
  return useQuery({ queryKey: KEY, queryFn: async () => demoInteraction.view() });
}

export function useOrganization(id: string) {
  return useQuery({
    queryKey: [...KEY, 'organization', id],
    queryFn: async () => demoInteraction.organization(id),
  });
}

function useChange<T, R = void>(perform: (input: T) => R) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (input: T) => perform(input),
    onSettled: () => client.invalidateQueries({ queryKey: KEY }),
  });
}

/** Оценка ответа — руководитель, одно касание (ТЗ 3.4, 11). Повторное касание снимает её. */
export function useRate() {
  return useChange((input: { id: string; rating: Rating | null }) =>
    demoInteraction.rate(input.id, input.rating),
  );
}

export function useAnswer() {
  return useChange((input: { id: string; on: string; number: string | null }) =>
    demoInteraction.answer(input.id, input),
  );
}

export function useAddLetter() {
  return useChange((input: NewLetter) => demoInteraction.add(input));
}

export function useNextStep() {
  return useChange((input: { id: string; next_step: string; next_step_on: string | null }) =>
    demoInteraction.setNextStep(input.id, input),
  );
}
