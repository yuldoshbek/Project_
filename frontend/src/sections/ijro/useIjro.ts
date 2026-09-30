/**
 * Данные раздела «Ижро».
 *
 * Сейчас сервер — `demoIjro` (`demo.ts`). Когда появится API раздела, меняются тела функций
 * ниже, а экран — нет. После каждой правки раздел перечитывается целиком: отметка меняет
 * признак жизни, признак жизни — ступень, ступень — ответы вопросов и стену.
 */

import { skipToken, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { DecisionKind } from '@/sections/pult/model';
import type { Role } from '@/shared/api/orbita';

import { demoIjro } from './demo';
import type { ApplyChoices, MarkKind, Stage, UploadInput } from './model';

const KEY = ['ijro'];

export function useIjro() {
  return useQuery({ queryKey: KEY, queryFn: async () => demoIjro.view() });
}

export function useAssignment(id: string) {
  return useQuery({ queryKey: [...KEY, 'card', id], queryFn: async () => demoIjro.card(id) });
}

/** Справка по проблемным поручениям — свой запрос: длинные тексты списку не нужны. */
export function useSpravka() {
  return useQuery({ queryKey: [...KEY, 'spravka'], queryFn: async () => demoIjro.spravka() });
}

function useChange<T, R = void>(perform: (input: T) => R) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (input: T) => perform(input),
    onSettled: () => client.invalidateQueries({ queryKey: KEY }),
  });
}

export interface MarkInput {
  id: string;
  kind: MarkKind;
  promised_on?: string | null;
  comment?: string | null;
  author: Role;
}

/** Контрольная отметка — одно касание, оба пользователя (V35). */
export function useMark() {
  return useChange((input: MarkInput) => demoIjro.mark(input.id, input, input.author));
}

export function useStage() {
  return useChange((input: { id: string; stage: Stage }) =>
    demoIjro.setStage(input.id, input.stage),
  );
}

export function useProblem() {
  return useChange((input: { id: string; problem: string; proposal: string }) =>
    demoIjro.setProblem(input.id, input.problem, input.proposal),
  );
}

export function useExtensionRequested() {
  return useChange((input: { id: string; value: boolean }) =>
    demoIjro.setExtensionRequested(input.id, input.value),
  );
}

export function useMatchPerson() {
  return useChange((input: { id: string; personId: string }) =>
    demoIjro.matchPerson(input.id, input.personId),
  );
}

/** Решение возвращает свой идентификатор — его держит «Отменить», как на Пульте. */
export function useDecide() {
  return useChange((input: { id: string; kind: DecisionKind }) =>
    demoIjro.decide(input.id, input.kind),
  );
}

export function useUndoDecision() {
  return useChange((decisionId: string) => demoIjro.undoDecision(decisionId));
}

export function useAsk() {
  return useChange((input: { id: string; text: string }) => demoIjro.ask(input.id, input.text));
}

export function useComment() {
  return useChange((input: { id: string; text: string; author: Role }) =>
    demoIjro.comment(input.id, input.text, input.author),
  );
}

/** «Разложить на задачу»: что покажет подтверждение — без записи. */
export function useTaskPrefill(id: string, enabled: boolean) {
  return useQuery({
    queryKey: [...KEY, 'prefill', id],
    queryFn: enabled ? async () => demoIjro.taskPrefill(id) : skipToken,
    refetchInterval: false,
  });
}

export function useCreateTask() {
  return useChange((id: string) => demoIjro.createTask(id));
}

/** Предпросмотр таблицы — без записи; не опрашивается: это снимок на момент загрузки. */
export function usePreview(input: UploadInput | null) {
  return useQuery({
    queryKey: [...KEY, 'preview', input?.file.name ?? null, input?.source ?? null],
    queryFn: input ? async () => demoIjro.preview(input) : skipToken,
    refetchInterval: false,
    staleTime: Infinity,
  });
}

export function useApply() {
  return useChange((input: { upload: UploadInput; choices: ApplyChoices }) =>
    demoIjro.apply(input.upload, input.choices),
  );
}
