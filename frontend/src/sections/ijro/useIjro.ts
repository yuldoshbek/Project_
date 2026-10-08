/**
 * Данные раздела «Ижро» и действия — `/api/v1/ijro…`.
 *
 * После каждой правки перечитываются раздел и Пульт: отметка меняет признак жизни,
 * признак жизни — ступень, ступень — ответы вопросов, стену и строку лестницы Пульта
 * (инвариант 2). Перечитываются и после отказа: отказ по версии значит, что картина на
 * экране устарела (инвариант 15). Решения и вопросы — те же `/decisions` и `/questions`,
 * что у кнопок Пульта, с объектом `ijro_assignment`.
 */

import { skipToken, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { DecisionKind } from '@/sections/pult/model';
import { request } from '@/shared/api/client';

import type {
  ApplyChoices,
  ApplyResult,
  AssignmentCard,
  IjroView,
  MarkKind,
  Preview,
  SpravkaLine,
  Stage,
  TaskPrefill,
  UploadInput,
} from './model';

const KEY = ['ijro'];
const BASE = '/api/v1/ijro';
const TARGET = 'ijro_assignment';

export function useIjro() {
  return useQuery({ queryKey: KEY, queryFn: () => request<IjroView>(BASE) });
}

export function useAssignment(id: string) {
  return useQuery({
    queryKey: [...KEY, 'card', id],
    queryFn: () => request<AssignmentCard>(`${BASE}/assignments/${id}`),
  });
}

/** Справка по проблемным поручениям — свой запрос: длинные тексты списку не нужны. */
export function useSpravka() {
  return useQuery({
    queryKey: [...KEY, 'spravka'],
    queryFn: () => request<SpravkaLine[]>(`${BASE}/spravka`),
  });
}

function useChange<T, R = void>(perform: (input: T) => Promise<R>, also: string[][] = []) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: perform,
    onSettled: () =>
      Promise.all(
        [KEY, ['pult'], ...also].map((queryKey) => client.invalidateQueries({ queryKey })),
      ),
  });
}

const assignment = (id: string, tail: string) => `${BASE}/assignments/${id}/${tail}`;

export interface MarkInput {
  id: string;
  kind: MarkKind;
  promised_on?: string | null;
  comment?: string | null;
}

/** Контрольная отметка — одно касание, оба пользователя (V35); автора подписывает сессия. */
export function useMark() {
  return useChange((input: MarkInput) =>
    request<{ id: string }>(assignment(input.id, 'marks'), {
      method: 'POST',
      body: {
        kind: input.kind,
        promised_on: input.promised_on ?? null,
        comment: input.comment ?? null,
      },
    }),
  );
}

export function useStage() {
  return useChange((input: { id: string; stage: Stage; version: number }) =>
    request<void>(assignment(input.id, 'stage'), {
      method: 'PUT',
      body: { stage: input.stage, version: input.version },
    }),
  );
}

export function useProblem() {
  return useChange((input: { id: string; problem: string; proposal: string; version: number }) =>
    request<void>(assignment(input.id, 'problem'), {
      method: 'PUT',
      body: { problem: input.problem, proposal: input.proposal, version: input.version },
    }),
  );
}

export function useExtensionRequested() {
  return useChange((input: { id: string; value: boolean; version: number }) =>
    request<void>(assignment(input.id, 'extension-request'), {
      method: 'PUT',
      body: { value: input.value, version: input.version },
    }),
  );
}

export function useMatchPerson() {
  return useChange((input: { id: string; personId: string; version: number }) =>
    request<void>(assignment(input.id, 'responsible'), {
      method: 'PUT',
      body: { person_id: input.personId, version: input.version },
    }),
  );
}

/** Решение возвращает свой идентификатор — его держит «Отменить», как на Пульте. */
export function useDecide() {
  return useChange(async (input: { id: string; kind: DecisionKind }) => {
    const made = await request<{ id: string }>('/api/v1/decisions', {
      method: 'POST',
      body: { target_type: TARGET, target_id: input.id, kind: input.kind },
    });
    return made.id;
  });
}

export function useUndoDecision() {
  return useChange((decisionId: string) =>
    request<void>(`/api/v1/decisions/${decisionId}`, { method: 'DELETE' }),
  );
}

export function useAsk() {
  return useChange(async (input: { id: string; text: string }) => {
    const asked = await request<{ id: string }>('/api/v1/questions', {
      method: 'POST',
      body: { target_type: TARGET, target_id: input.id, text: input.text },
    });
    return asked.id;
  });
}

export function useComment() {
  return useChange((input: { id: string; text: string }) =>
    request<{ id: string }>(assignment(input.id, 'comments'), {
      method: 'POST',
      body: { text: input.text },
    }),
  );
}

/** «Разложить на задачу»: что покажет подтверждение — без записи. */
export function useTaskPrefill(id: string, enabled: boolean) {
  return useQuery({
    queryKey: [...KEY, 'prefill', id],
    queryFn: enabled ? () => request<TaskPrefill>(assignment(id, 'task-prefill')) : skipToken,
    refetchInterval: false,
  });
}

/** Задача из поручения появляется и в «Задачах», и в их календаре. */
export function useCreateTask() {
  return useChange(
    (id: string) =>
      request<{ id: string; code: string }>(assignment(id, 'tasks'), { method: 'POST' }),
    [['tasks'], ['calendar'], ['captures']],
  );
}

/**
 * Предпросмотр таблицы: файл уходит телом запроса, ответ — партия на подтверждение (ТЗ 7).
 * Не опрашивается и не повторяется: это снимок на момент загрузки, а каждый запрос заводит
 * партию. Новый выбор того же файла — новый ключ (`lastModified`), то есть новый разбор.
 */
export function usePreview(input: UploadInput | null) {
  return useQuery({
    queryKey: [
      ...KEY,
      'preview',
      input?.file.name ?? null,
      input?.file.size ?? null,
      input?.file.lastModified ?? null,
      input?.source ?? null,
    ],
    queryFn: input
      ? () =>
          request<Preview>(`${BASE}/imports`, {
            method: 'POST',
            body: input.file,
            query: { file: input.file.name, source: input.source, table_year: input.table_year },
          })
      : skipToken,
    refetchInterval: false,
    refetchOnWindowFocus: false,
    retry: false,
    staleTime: Infinity,
  });
}

export function useApply() {
  return useChange(
    (input: { batchId: string; choices: ApplyChoices }) =>
      request<ApplyResult>(`${BASE}/imports/${input.batchId}/apply`, {
        method: 'POST',
        body: input.choices,
      }),
    [['tasks']],
  );
}
