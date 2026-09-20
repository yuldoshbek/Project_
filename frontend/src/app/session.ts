/**
 * Кто открыл систему и отвечает ли она.
 *
 * Два запроса, которые идут первыми и нужны везде: `/api/me` — кто вошёл, `/api/health` —
 * что выложено. Оба вынесены сюда, чтобы на экране не оказалось двух источников правды о
 * текущем пользователе.
 *
 * Отсутствие сессии (401) не повторяется: повтор не создаст сессию, а мигание «загрузка —
 * отказ — загрузка» выглядит как поломка. Экран показывает «откройте по своей ссылке» и
 * ждёт действия человека.
 */

import { useQuery } from '@tanstack/react-query';

import { ApiError } from '@/shared/api/client';
import { api, POLL_INTERVAL_MS } from '@/shared/api/orbita';

export function useCurrentUser() {
  return useQuery({
    queryKey: ['me'],
    queryFn: api.me,
    retry: (attempt, error) => !(error instanceof ApiError && error.needsLink) && attempt < 2,
    staleTime: POLL_INTERVAL_MS,
  });
}

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: api.health,
    // Состояние спрашивается реже данных: оно меняется только при выкладке.
    refetchInterval: 60_000,
    retry: 1,
  });
}
