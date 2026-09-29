/**
 * Данные Управления.
 *
 * Сейчас сервер — `demoManagement`; устройства и перевыпуск ссылок — настоящий API блока 0
 * (`LinkCard`). Когда появится API раздела, меняются тела функций ниже, а экран — нет.
 * После каждой правки раздел перечитывается целиком: пороги меняют и обход, и числа.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { Role } from '@/shared/api/orbita';

import { demoManagement } from './demo';
import type { DictionaryKind, OrganizationKind, RoundAction, ThresholdKey } from './model';

const KEY = ['management'];

export function useManagement() {
  return useQuery({ queryKey: KEY, queryFn: async () => demoManagement.view() });
}

function useChange<T>(perform: (input: T) => void) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (input: T) => perform(input),
    onSettled: () => client.invalidateQueries({ queryKey: KEY }),
  });
}

export function useRoundAction() {
  return useChange((input: { id: string; action: RoundAction; input?: string }) =>
    demoManagement.act(input.id, input.action, input.input),
  );
}

/** Сколько строк сделает сигналом порог с этим значением — без записи. */
export function useImpact(key: ThresholdKey, value: number | string, enabled: boolean) {
  return useQuery({
    queryKey: [...KEY, 'impact', key, value],
    queryFn: async () => demoManagement.impact(key, value),
    enabled,
  });
}

export function useSaveThreshold() {
  return useChange((input: { key: ThresholdKey; value: number | string; version: number }) => {
    demoManagement.setThreshold(input.key, input.value, input.version);
  });
}

/** Правка приходит с версией, которую видел человек (инвариант 15); новое значение — без. */
export type DictionaryChange =
  | {
      op: 'rename';
      kind: DictionaryKind;
      id: string;
      name: string;
      version: number;
      orgKind?: OrganizationKind;
    }
  | { op: 'toggle'; kind: DictionaryKind; id: string; version: number }
  | { op: 'move'; kind: DictionaryKind; id: string; step: -1 | 1; version: number }
  | { op: 'add'; kind: DictionaryKind; name: string; orgKind?: OrganizationKind };

export function useDictionaryChange() {
  return useChange((change: DictionaryChange) => {
    switch (change.op) {
      case 'rename':
        demoManagement.rename(change.kind, change.id, change.name, change.version, change.orgKind);
        return;
      case 'toggle':
        demoManagement.toggle(change.kind, change.id, change.version);
        return;
      case 'move':
        demoManagement.move(change.kind, change.id, change.step, change.version);
        return;
      case 'add':
        demoManagement.add(change.kind, change.name, change.orgKind);
    }
  });
}

export type StepChange =
  | { op: 'save'; type: string; id?: string; name: string; offset_days: number; version?: number }
  | { op: 'remove'; type: string; id: string; version: number };

export function useStepChange() {
  return useChange((change: StepChange) => {
    if (change.op === 'remove') {
      demoManagement.removeStep(change.type, change.id, change.version);
      return;
    }
    demoManagement.saveStep(change.type, {
      ...(change.id ? { id: change.id } : {}),
      ...(change.version === undefined ? {} : { version: change.version }),
      name: change.name,
      offset_days: change.offset_days,
    });
  });
}

/**
 * Настоящий перевыпуск прошёл — вымышленный сервер запоминает дату, и карточка не
 * возвращается к выдуманной после смены вкладки. С API дату отдаст сервер сам.
 */
export function useLinkIssued() {
  const client = useQueryClient();
  return (role: Role, issuedAt: string) => {
    demoManagement.linkIssued(role, issuedAt);
    void client.invalidateQueries({ queryKey: KEY });
  };
}
