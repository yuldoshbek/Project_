/**
 * Режим работы и клиент запросов вместе.
 *
 * Экраны используют и то и другое, и разделять обёртки значило бы получать в тестах
 * «No QueryClient set» вместо проверяемого поведения. Клиент создаётся свой на каждый
 * вызов: общий кеш переносил бы данные из теста в тест и делал бы порядок значимым.
 *
 * Пришла на место `WithSession`: входа в системе больше нет (ADR-0026), и обёртывать
 * тест сессией стало нечем. Осталось единственное, что экран о человеке знает, — в каком
 * режиме он работает.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { configureApi } from '../shared/api/client';
import { DEFAULT_MODE, ModeContext, type Mode } from '../shared/mode/ModeContext';

export function WithMode({ children, mode = DEFAULT_MODE }: { children: ReactNode; mode?: Mode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });

  // То же, что делает `ModeProvider` в приложении. Без этого клиент API в тестах не знал
  // бы, чем подписывать запрос, и пропажу заголовка не заметил бы ни один тест: они все
  // и так проходили бы.
  configureApi(() => mode);

  const value = { mode, setMode: () => {} };

  return (
    <QueryClientProvider client={client}>
      <ModeContext.Provider value={value}>{children}</ModeContext.Provider>
    </QueryClientProvider>
  );
}
