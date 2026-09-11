/**
 * Сессия и клиент запросов вместе.
 *
 * Экраны используют и то и другое, и разделять обёртки значило бы получать в тестах
 * «No QueryClient set» вместо проверяемого поведения. Клиент создаётся свой на каждый
 * вызов: общий кеш переносил бы данные из теста в тест и делал бы порядок значимым.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import type { SessionValue } from '../shared/auth/SessionContext';
import { SessionContext } from '../shared/auth/SessionContext';
import { ASSISTANT, sessionOf } from './profiles';

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

  return (
    <QueryClientProvider client={client}>
      <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
    </QueryClientProvider>
  );
}
