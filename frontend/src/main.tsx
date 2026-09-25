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
import { QUERY_DEFAULTS } from '@/shared/api/queries';
import '@/shared/i18n';
import '@/styles/app.css';

// Опрос и его исключения — shared/api/queries.ts. Возврат на вкладку обновляет сразу:
// руководитель открывает систему и должен видеть сегодняшнее, а не то, что было утром.
const queryClient = new QueryClient({ defaultOptions: { queries: QUERY_DEFAULTS } });

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
