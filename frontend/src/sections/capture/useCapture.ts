/**
 * Данные Захвата: недавние записи и запись новой.
 *
 * Сейчас сервер входящих — `demoCaptures`; задача заводится настоящим API «Задач»
 * (`useCreateTask`), и в недавние попадает её след. Когда появится API Захвата, меняются
 * тела функций ниже.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { demoCaptures } from './demo';
import type { Capture, NewCapture } from './model';

export function useCaptures() {
  return useQuery({
    queryKey: ['captures'],
    queryFn: async () => demoCaptures.view(),
  });
}

export function useSaveCapture(author: Capture['author']) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (input: NewCapture) => demoCaptures.save(input, author),
    onSettled: () => client.invalidateQueries({ queryKey: ['captures'] }),
  });
}

/** След заведённой задачи в недавних — чтобы было видно, куда ушла запись. */
export function useRememberTask(author: Capture['author']) {
  const client = useQueryClient();
  return (title: string, dueOn: string | null) => {
    demoCaptures.remember(title, dueOn, author);
    void client.invalidateQueries({ queryKey: ['captures'] });
  };
}
