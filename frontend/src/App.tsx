import { QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';

import { queryClient } from './app/queryClient';
import { router } from './app/router';
import { AuthProvider } from './shared/auth/AuthProvider';

/**
 * Провайдер сессии стоит снаружи маршрутизатора: состояние входа переживает переходы
 * между экранами, а восстановление сессии при запуске происходит один раз, а не на
 * каждом экране.
 */
export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>
  );
}
