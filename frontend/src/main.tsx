/**
 * Точка входа.
 *
 * Здесь собирается всё вместе: стили, языки, кеш запросов, тема, маршруты. Порядок
 * провайдеров имеет значение: тема стоит выше маршрутов, потому что переключатель темы живёт
 * в оболочке, а оболочка — внутри маршрута.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from '@tanstack/react-router';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { router } from '@/app/router';
import { pultQuery } from '@/sections/pult/usePult';
import { ThemeProvider } from '@/app/theme';
import { QUERY_DEFAULTS } from '@/shared/api/queries';
import '@/shared/i18n';
import { keepLastPicture, restoreLastPicture } from '@/shared/api/offline';
import '@/styles/app.css';

// Опрос и его исключения — shared/api/queries.ts. Возврат на вкладку обновляет сразу:
// руководитель открывает систему и должен видеть сегодняшнее, а не то, что было утром.
const queryClient = new QueryClient({ defaultOptions: { queries: QUERY_DEFAULTS } });

// Последняя картина Пульта — сразу, ещё до ответа сервера, и без связи (`offline.ts`).
restoreLastPicture(queryClient);
keepLastPicture(queryClient);

// Пульт — первый экран руководителя: его данные запрашиваются сразу, вместе с `/api/me`, а
// не после того, как оболочка узнает, кто вошёл. На 4G это минус один круг до сервера
// (замер первого экрана, критерий 4 блока 3: ответ Пульта стартовал на 330 мс позже).
// Нет сессии — запрос вернёт отказ, и экран входа покажет оболочка, как и без него.
if (window.location.pathname === '/') void queryClient.prefetchQuery(pultQuery());

const root = document.getElementById('root');
if (!root) throw new Error('нет элемента #root: проверьте index.html');

createRoot(root).render(
  <StrictMode>
    {/* Движение — только CSS: `prefers-reduced-motion` гасит его правилом в `app.css`. */}
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
