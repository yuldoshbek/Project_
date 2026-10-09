/**
 * Данные раздела «Доклады и мероприятия» и действия — `/api/v1/preparations…`.
 *
 * После правки перечитываются раздел и Пульт: полученные сведения меняют «кто задерживает»,
 * этап — ступень строки лестницы (инвариант 2). Перечитываются и после отказа по версии.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { request } from '@/shared/api/client';
import { fileLink, uploadTo } from '@/shared/api/upload';

import type {
  NewPreparation,
  NewRequest,
  PreparationCard,
  PrepStage,
  ReportsView,
  VersionState,
} from './model';

const KEY = ['preparations'];
const BASE = '/api/v1/preparations';

export function useReports() {
  return useQuery({ queryKey: KEY, queryFn: () => request<ReportsView>(BASE) });
}

export function usePreparation(id: string) {
  return useQuery({
    queryKey: [...KEY, id],
    queryFn: () => request<PreparationCard>(`${BASE}/${id}`),
  });
}

function useChange<T, R = void>(perform: (input: T) => Promise<R>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: perform,
    onSettled: () =>
      Promise.all(
        [KEY, ['pult'], ['calendar']].map((queryKey) => client.invalidateQueries({ queryKey })),
      ),
  });
}

export function useCreatePreparation() {
  return useChange((input: NewPreparation) =>
    request<{ id: string }>(BASE, { method: 'POST', body: input }),
  );
}

export function useStage() {
  return useChange((input: { id: string; stage: PrepStage; version: number }) =>
    request<void>(`${BASE}/${input.id}/stage`, {
      method: 'PUT',
      body: { stage: input.stage, version: input.version },
    }),
  );
}

export function useAddItem() {
  return useChange((input: { id: string; text: string }) =>
    request<{ id: string }>(`${BASE}/${input.id}/items`, {
      method: 'POST',
      body: { text: input.text },
    }),
  );
}

export function useToggleItem() {
  return useChange((input: { id: string; itemId: string; done: boolean; version: number }) =>
    request<void>(`${BASE}/${input.id}/items/${input.itemId}`, {
      method: 'PUT',
      body: { done: input.done, version: input.version },
    }),
  );
}

export function useAddRequest() {
  return useChange((input: { id: string; request: NewRequest }) =>
    request<{ id: string }>(`${BASE}/${input.id}/requests`, {
      method: 'POST',
      body: input.request,
    }),
  );
}

export function useReceive() {
  return useChange(
    (input: { id: string; requestId: string; received_on: string | null; version: number }) =>
      request<void>(`${BASE}/${input.id}/requests/${input.requestId}/received`, {
        method: 'PUT',
        body: { received_on: input.received_on, version: input.version },
      }),
  );
}

interface StartedVersion {
  version_id: string;
  file_id: string;
  upload: { url: string; method: string; headers: Record<string, string> };
}

/** Новая версия презентации: ссылка от API, файл и проверка — общей загрузкой (`uploadTo`). */
export function useUploadVersion() {
  return useChange(async (input: { id: string; file: File }) => {
    const started = await request<StartedVersion>(`${BASE}/${input.id}/versions`, {
      method: 'POST',
      body: {
        name: input.file.name,
        content_type: input.file.type || 'application/octet-stream',
        size: input.file.size,
      },
    });
    await uploadTo(started.file_id, started.upload, input.file);
    return started.version_id;
  });
}

export { fileLink };

export function useVersionState() {
  return useChange(
    (input: { id: string; versionId: string; state: VersionState; version: number }) =>
      request<void>(`${BASE}/${input.id}/versions/${input.versionId}/state`, {
        method: 'PUT',
        body: { state: input.state, version: input.version },
      }),
  );
}

export function useAddComment() {
  return useChange((input: { id: string; versionId: string; slide: number; text: string }) =>
    request<{ id: string }>(`${BASE}/${input.id}/versions/${input.versionId}/comments`, {
      method: 'POST',
      body: { slide: input.slide, text: input.text },
    }),
  );
}

export function useFixComment() {
  return useChange((input: { id: string; commentId: string; fixed: boolean; version: number }) =>
    request<void>(`${BASE}/${input.id}/comments/${input.commentId}/fixed`, {
      method: 'PUT',
      body: { fixed: input.fixed, version: input.version },
    }),
  );
}
