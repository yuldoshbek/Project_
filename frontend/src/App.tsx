import { QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';

import { queryClient } from './app/queryClient';
import { router } from './app/router';
import { ModeProvider } from './shared/mode/ModeProvider';

/**
 * Провайдер режима стоит снаружи маршрутизатора: выбранный режим переживает переходы
 * между экранами, а клиент API узнаёт о нём один раз, а не на каждом экране.
 *
 * Входа в системе нет (ADR-0026), поэтому провайдера сессии здесь тоже нет: приложение
 * открывается сразу, а кого до него допускать, решает периметр.
 */
export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ModeProvider>
        <RouterProvider router={router} />
      </ModeProvider>
    </QueryClientProvider>
  );
}
