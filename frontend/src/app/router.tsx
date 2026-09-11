import type { RouteObject } from 'react-router-dom';
import { createBrowserRouter } from 'react-router-dom';

import { ProjectsPage } from '../features/projects/ProjectsPage';
import { AppLayout } from '../layout/AppLayout';
import { ForbiddenPage } from '../pages/ForbiddenPage';
import { LoginPage } from '../pages/LoginPage';
import { NotFoundPage } from '../pages/NotFoundPage';
import { PlaceholderPage } from '../pages/PlaceholderPage';
import { RequireSession } from './RequireSession';
import { NAV_ITEMS, ROUTES } from './routes';

/** Готовые экраны по адресу. Заглушка остаётся там, где экрана ещё нет. */
const SCREENS: Record<string, React.ReactElement> = {
  [ROUTES.projects]: <ProjectsPage />,
};

/**
 * Маршруты приложения.
 *
 * Разделы собираются из `NAV_ITEMS`: меню и маршруты обязаны совпадать, а два списка
 * рано или поздно расходятся. По мере готовности экранов `PlaceholderPage` заменяется
 * настоящим компонентом — построчно, по одному тикету.
 */
export const routes: RouteObject[] = [
  // Вход — вне оболочки: меню и хлебные крошки тому, кто ещё не вошёл, ничего не
  // говорят и только мешают найти два поля.
  { path: ROUTES.login, element: <LoginPage /> },
  {
    element: <RequireSession />,
    errorElement: <NotFoundPage />,
    children: [
      {
        path: ROUTES.dashboard,
        element: <AppLayout />,
        children: [
          ...NAV_ITEMS.map((item): RouteObject => {
            const element = SCREENS[item.to] ?? (
              <PlaceholderPage titleKey={item.labelKey} ticket={item.ticket} />
            );
            return item.end === true
              ? { index: true, element }
              : { path: item.to.slice(1), element };
          }),
          { path: ROUTES.forbidden.slice(1), element: <ForbiddenPage /> },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

export const router = createBrowserRouter(routes);
