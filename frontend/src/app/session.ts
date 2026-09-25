/**
 * Кто открыл систему и отвечает ли она.
 *
 * Два запроса, которые идут первыми и нужны везде: `/api/me` — кто вошёл, `/api/health` —
 * что выложено. Оба вынесены сюда, чтобы на экране не оказалось двух источников правды о
 * текущем пользователе. Частота и повторы — в `shared/api/queries.ts`.
 */

import { useQuery } from '@tanstack/react-query';

import { currentUserQuery, healthQuery } from '@/shared/api/queries';

export function useCurrentUser() {
  return useQuery(currentUserQuery());
}

export function useHealth() {
  return useQuery(healthQuery());
}
