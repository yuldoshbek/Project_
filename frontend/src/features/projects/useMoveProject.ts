/**
 * Перенос проекта в другой статус.
 *
 * **Карточка переезжает сразу, до ответа сервера.** Доска, на которой отпущенная карточка
 * сначала возвращается в исходную колонку и через полсекунды прыгает в новую, читается
 * как сбой. Если сервер откажет, карточка возвращается туда, откуда её взяли, — и об этом
 * говорит сообщение рядом с доской, словами сервера, а не своими.
 *
 * После ответа портфель перечитывается целиком: светофор завершённого проекта становится
 * серым, и считает это сервер (ADR-0005), а не доска.
 */

import type { QueryKey } from '@tanstack/react-query';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import type { Project } from './api';
import { updateProjectStatus } from './api';

export interface MoveRequest {
  project: Project;
  status: string;
  reason?: string;
}

export function useMoveProject(queryKey: QueryKey) {
  const client = useQueryClient();

  return useMutation({
    mutationFn: ({ project, status, reason }: MoveRequest) =>
      updateProjectStatus(project.id, status, reason),

    onMutate: async ({ project, status, reason }: MoveRequest) => {
      // Незавершённое чтение портфеля вернуло бы старый статус поверх нового.
      await client.cancelQueries({ queryKey });
      const previous = client.getQueryData<Project[]>(queryKey);
      client.setQueryData<Project[]>(queryKey, (list) =>
        list?.map((item) =>
          item.id === project.id
            ? { ...item, status_code: status, status_reason: reason ?? item.status_reason }
            : item,
        ),
      );
      return { previous };
    },

    onError: (_error, _request, context) => {
      if (context?.previous !== undefined) client.setQueryData(queryKey, context.previous);
    },

    onSettled: () => client.invalidateQueries({ queryKey: ['projects'] }),
  });
}
