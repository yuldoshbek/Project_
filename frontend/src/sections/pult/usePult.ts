/**
 * Данные Пульта и три действия над ними: решить, спросить, отменить.
 *
 * Устроено так же, как будет устроено с API: запрос через TanStack Query, действие —
 * мутация, после неё лестница перечитывается у сервера. Экран не пересчитывает счётчики
 * сам — после решения он получает новые числа от того же источника (инвариант 2).
 *
 * Сейчас сервер — `demoPult`. Когда появится `GET /api/v1/pult`, меняются тела трёх
 * функций ниже и больше ничего.
 */

import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { demoPult } from './demo';
import type { DecisionKind, PultView } from './model';

export function pultQuery() {
  return queryOptions({
    queryKey: ['pult'],
    queryFn: async (): Promise<PultView> => demoPult.view(),
  });
}

export function usePult() {
  return useQuery(pultQuery());
}

type Action =
  | { type: 'decide'; key: string; kind: DecisionKind }
  | { type: 'ask'; key: string; text: string }
  | { type: 'undo'; key: string };

export function usePultAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (action: Action) => {
      if (action.type === 'decide') demoPult.decide(action.key, action.kind);
      if (action.type === 'ask') demoPult.ask(action.key, action.text);
      if (action.type === 'undo') demoPult.undo(action.key);
    },
    onSuccess: () => client.invalidateQueries({ queryKey: pultQuery().queryKey }),
  });
}
