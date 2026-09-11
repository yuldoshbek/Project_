/**
 * Сессия и клиент запросов вместе.
 *
 * Экраны используют и то и другое, и разделять обёртки значило бы получать в тестах
 * «No QueryClient set» вместо проверяемого поведения. Клиент создаётся свой на каждый
 * вызов: общий кеш переносил бы данные из теста в тест и делал бы порядок значимым.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { configureApi } from '../shared/api/client';
import type { SessionValue } from '../shared/auth/SessionContext';
import { SessionContext } from '../shared/auth/SessionContext';
import { ASSISTANT, sessionOf } from './profiles';

/** Токен вошедшего — такой же условный, как и профиль рядом. */
export const TEST_ACCESS_TOKEN = 'test-access-token';

export function WithSession({
  children,
  value = sessionOf(ASSISTANT, 'signed-in'),
}: {
  children: ReactNode;
  value?: SessionValue;
}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });

  // То же, что делает `AuthProvider` в приложении. Без этого клиент API в тестах не
  // знает, откуда брать токен, и ни один запрос не уходит с ним — а значит, пропажу
  // заголовка `Authorization` не заметил бы ни один тест: они все и так проходили бы.
  configureApi(
    () => (value.status === 'signed-in' ? TEST_ACCESS_TOKEN : null),
    () => {},
  );

  return (
    <QueryClientProvider client={client}>
      <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
    </QueryClientProvider>
  );
}
