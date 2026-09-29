/**
 * Данные Управления — `/api/v1/management…`; устройства и перевыпуск ссылок — `/api/access/…`
 * (`AccessTab`).
 *
 * После каждой правки раздел перечитывается целиком: пороги меняют и обход, и числа. И
 * перечитывается то, что правка меняет на других экранах (инвариант 2): действие обхода —
 * Пульт, проекты, задачи, программы, календарь и захват (у недавней записи — срок задачи);
 * порог — их же; справочник и шаблон вех — формы и названия в проектах, задачах и
 * программах. Перечитывается и после отказа: отказ по версии значит, что картина на экране
 * устарела (инвариант 15).
 */

import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { request } from '@/shared/api/client';

import type {
  DictionaryKind,
  ManagementView,
  OrganizationKind,
  RoundAction,
  RoundItem,
  ThresholdKey,
} from './model';

const BASE = '/api/v1/management';
const KEY = ['management'];

const SECTIONS = [['pult'], ['projects'], ['tasks'], ['programs'], ['calendar'], ['captures']];
const FORMS = [['dictionaries'], ['organizations'], ['projects'], ['tasks'], ['programs']];

/** Один набор параметров на ключ: его читает и вкладка «Сводка» Пульта — время из порога. */
export function managementQuery() {
  return queryOptions({ queryKey: KEY, queryFn: () => request<ManagementView>(BASE) });
}

export function useManagement() {
  return useQuery(managementQuery());
}

function useChange<T, R = void>(perform: (input: T) => Promise<R>, also: string[][]) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: perform,
    onSettled: () =>
      Promise.all([KEY, ...also].map((queryKey) => client.invalidateQueries({ queryKey }))),
  });
}

export function useRoundAction() {
  return useChange(
    (input: { item: RoundItem; action: RoundAction; input?: string }) =>
      request<void>(`${BASE}/round`, {
        method: 'POST',
        body: {
          reason: input.item.reason,
          record_kind: input.item.record.kind,
          record_id: input.item.record.id,
          action: input.action,
          version: input.item.record.version,
          ...(input.input === undefined ? {} : { input: input.input }),
        },
      }),
    SECTIONS,
  );
}

/** Сколько строк сделает сигналом порог с этим значением — без записи. */
export function useImpact(key: ThresholdKey, value: number | string, enabled: boolean) {
  return useQuery({
    queryKey: [...KEY, 'impact', key, value],
    queryFn: async () =>
      (
        await request<{ affected: number | null }>(`${BASE}/thresholds/${key}/preview`, {
          query: { value: String(value) },
        })
      ).affected,
    enabled,
  });
}

export function useSaveThreshold() {
  return useChange(
    (input: { key: ThresholdKey; value: number | string; version: number }) =>
      request<void>(`${BASE}/thresholds/${input.key}`, {
        method: 'PUT',
        body: { value: input.value, version: input.version },
      }),
    SECTIONS,
  );
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

async function changeDictionary(change: DictionaryChange): Promise<void> {
  const base = `${BASE}/dictionaries/${change.kind}`;
  switch (change.op) {
    case 'rename':
      await request(`${base}/${change.id}`, {
        method: 'PUT',
        body: {
          name: change.name,
          version: change.version,
          ...(change.orgKind ? { org_kind: change.orgKind } : {}),
        },
      });
      return;
    case 'toggle':
      await request(`${base}/${change.id}/toggle`, {
        method: 'POST',
        body: { version: change.version },
      });
      return;
    case 'move':
      await request(`${base}/${change.id}/move`, {
        method: 'POST',
        body: { step: change.step, version: change.version },
      });
      return;
    case 'add':
      await request(base, {
        method: 'POST',
        body: { name: change.name, ...(change.orgKind ? { org_kind: change.orgKind } : {}) },
      });
  }
}

export function useDictionaryChange() {
  return useChange(changeDictionary, FORMS);
}

export type StepChange =
  | { op: 'save'; type: string; id?: string; name: string; offset_days: number; version?: number }
  | { op: 'remove'; type: string; id: string; version: number };

async function changeStep(change: StepChange): Promise<void> {
  const base = `${BASE}/templates/${change.type}/steps`;
  if (change.op === 'remove') {
    await request(`${base}/${change.id}`, {
      method: 'DELETE',
      query: { version: change.version },
    });
    return;
  }
  const body = { name: change.name, offset_days: change.offset_days };
  if (change.id) {
    await request(`${base}/${change.id}`, {
      method: 'PUT',
      body: { ...body, version: change.version },
    });
    return;
  }
  await request(base, { method: 'POST', body });
}

export function useStepChange() {
  return useChange(changeStep, FORMS);
}
