/**
 * Данные раздела «Идеи и карты» и действия — `/api/v1/ideas…`, `/api/v1/maps…`.
 *
 * Открытая карта перечитывается раз в 5 секунд: правка второго пользователя появляется без
 * перезагрузки (ТЗ 11, критерий блока 3), а постоянного соединения нет — обновление идёт
 * опросом ([ADR-0034](../../../../docs/adr/ADR-0034-near-real-time.md)). Решение по идее
 * заводит проект или задачу — перечитываются и их разделы, и Пульт.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { request } from '@/shared/api/client';

import type { IdeasView, MapCard, MapMode, Outcome } from './model';

const KEY = ['ideas'];
const MAP_KEY = ['maps'];

/** Как часто открытая карта спрашивает о правках второго пользователя. */
export const MAP_POLL_MS = 5_000;

export function useIdeas() {
  return useQuery({ queryKey: KEY, queryFn: () => request<IdeasView>('/api/v1/ideas') });
}

export function useMap(id: string, live = true) {
  return useQuery({
    queryKey: [...MAP_KEY, id],
    queryFn: () => request<MapCard>(`/api/v1/maps/${id}`),
    refetchInterval: live ? MAP_POLL_MS : false,
  });
}

function useChange<T, R = void>(perform: (input: T) => Promise<R>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: perform,
    onSettled: () =>
      Promise.all(
        [KEY, MAP_KEY, ['pult'], ['projects'], ['tasks']].map((queryKey) =>
          client.invalidateQueries({ queryKey }),
        ),
      ),
  });
}

export function useCreateIdea() {
  return useChange((text: string) =>
    request<{ id: string }>('/api/v1/ideas', { method: 'POST', body: { text } }),
  );
}

export function useToReview() {
  return useChange((input: { id: string; version: number }) =>
    request<void>(`/api/v1/ideas/${input.id}/review`, {
      method: 'PUT',
      body: { version: input.version },
    }),
  );
}

export function useDecide() {
  return useChange(
    (input: { id: string; outcome: Outcome; type_code: string | null; version: number }) =>
      request<{ created_id: string | null }>(`/api/v1/ideas/${input.id}/decision`, {
        method: 'POST',
        body: { outcome: input.outcome, type_code: input.type_code, version: input.version },
      }),
  );
}

export function useCreateMap() {
  return useChange((input: { title: string; mode: MapMode }) =>
    request<{ id: string }>('/api/v1/maps', { method: 'POST', body: input }),
  );
}

export function useEditMap() {
  return useChange((input: { id: string; title: string; mode: MapMode; version: number }) =>
    request<void>(`/api/v1/maps/${input.id}`, {
      method: 'PUT',
      body: { title: input.title, mode: input.mode, version: input.version },
    }),
  );
}

const nodes = (mapId: string) => `/api/v1/maps/${mapId}/nodes`;

export function useAddNode() {
  return useChange(
    (input: { mapId: string; text: string; parent_id: string | null; x: number; y: number }) =>
      request<{ id: string }>(nodes(input.mapId), {
        method: 'POST',
        body: { text: input.text, parent_id: input.parent_id, x: input.x, y: input.y },
      }),
  );
}

export function useEditNode() {
  return useChange((input: { mapId: string; id: string; text: string; version: number }) =>
    request<void>(`${nodes(input.mapId)}/${input.id}`, {
      method: 'PUT',
      body: { text: input.text, version: input.version },
    }),
  );
}

export function useMoveNode() {
  return useChange((input: { mapId: string; id: string; x: number; y: number; version: number }) =>
    request<void>(`${nodes(input.mapId)}/${input.id}/position`, {
      method: 'PUT',
      body: { x: input.x, y: input.y, version: input.version },
    }),
  );
}

export function useSetParent() {
  return useChange(
    (input: { mapId: string; id: string; parent_id: string | null; version: number }) =>
      request<void>(`${nodes(input.mapId)}/${input.id}/parent`, {
        method: 'PUT',
        body: { parent_id: input.parent_id, version: input.version },
      }),
  );
}

export function useDeleteNode() {
  return useChange((input: { mapId: string; id: string; version: number }) =>
    request<{ deleted: number }>(`${nodes(input.mapId)}/${input.id}?version=${input.version}`, {
      method: 'DELETE',
    }),
  );
}

export function useConvertNode() {
  return useChange(
    (input: {
      mapId: string;
      id: string;
      kind: 'project' | 'task';
      type_code: string | null;
      version: number;
    }) =>
      request<{ id: string }>(`${nodes(input.mapId)}/${input.id}/convert`, {
        method: 'POST',
        body: { kind: input.kind, type_code: input.type_code, version: input.version },
      }),
  );
}
