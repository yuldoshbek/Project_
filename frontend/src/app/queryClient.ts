import { QueryClient } from '@tanstack/react-query';

/**
 * Настройки загрузки данных.
 *
 * Система про сроки и просрочки: показывать вчерашнее число «горящих» задач хуже, чем
 * не показывать ничего. Поэтому данные считаются устаревшими быстро, а возврат на
 * вкладку вызывает перезапрос.
 *
 * Повтор после ошибки — только для сетевых сбоев. Ответы 403 и 404 повторять
 * бессмысленно: прав от повтора не прибавится (ADR-0003).
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: true,
      retry: (failureCount, error) => failureCount < 2 && !isClientError(error),
    },
    mutations: {
      retry: false,
    },
  },
});

/** Ошибка запроса, у которой известен код ответа. Полный тип придёт с клиентом API. */
interface HttpErrorLike {
  status?: number;
}

function isClientError(error: unknown): boolean {
  const status = (error as HttpErrorLike | null)?.status;
  return typeof status === 'number' && status >= 400 && status < 500;
}
