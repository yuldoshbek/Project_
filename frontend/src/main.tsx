/**
 * Точка входа.
 *
 * Здесь собирается всё вместе: стили, языки, кеш запросов, тема, маршруты. Порядок
 * провайдеров имеет значение: тема стоит выше маршрутов, потому что переключатель темы живёт
 * в оболочке, а оболочка — внутри маршрута.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from '@tanstack/react-router';
import { MotionConfig } from 'motion/react';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { router } from '@/app/router';
import { ThemeProvider } from '@/app/theme';
import { POLL_INTERVAL_MS } from '@/shared/api/client';
import '@/shared/i18n';
import '@/styles/app.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Обновление опросом, а не постоянным соединением: прокси Netlify закрывает
      // соединение через 26 секунд (ADR-0034). Возврат на вкладку обновляет сразу —
      // руководитель открывает систему и должен видеть сегодняшнее, а не то, что было
      // утром.
      refetchInterval: POLL_INTERVAL_MS,
      refetchOnWindowFocus: true,
      staleTime: POLL_INTERVAL_MS,
      retry: 1,
    },
  },
});

const root = document.getElementById('root');
if (!root) throw new Error('нет элемента #root: проверьте index.html');

createRoot(root).render(
  <StrictMode>
    {/* reducedMotion="user": кто попросил меньше движения в системе, тот его не получает.
        Анимация объясняет изменение, а не украшает, и без неё система остаётся рабочей. */}
    <MotionConfig reducedMotion="user">
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </ThemeProvider>
    </MotionConfig>
  </StrictMode>,
);
