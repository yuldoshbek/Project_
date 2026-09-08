import type { RouteObject } from 'react-router-dom';
import { createBrowserRouter } from 'react-router-dom';

import { AppLayout } from '../layout/AppLayout';
import { ForbiddenPage } from '../pages/ForbiddenPage';
import { NotFoundPage } from '../pages/NotFoundPage';
import { PlaceholderPage } from '../pages/PlaceholderPage';
import { NAV_ITEMS, ROUTES } from './routes';

/**
 * Маршруты приложения.
 *
 * Разделы собираются из `NAV_ITEMS`: меню и маршруты обязаны совпадать, а два списка
 * рано или поздно расходятся. По мере готовности экранов `PlaceholderPage` заменяется
 * настоящим компонентом — построчно, по одному тикету.
 */
export const routes: RouteObject[] = [
  {
    path: ROUTES.dashboard,
    element: <AppLayout />,
    errorElement: <NotFoundPage />,
    children: [
      ...NAV_ITEMS.map((item): RouteObject => {
        const element = <PlaceholderPage titleKey={item.labelKey} ticket={item.ticket} />;
        return item.end === true ? { index: true, element } : { path: item.to.slice(1), element };
      }),
      { path: ROUTES.forbidden.slice(1), element: <ForbiddenPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
];

export const router = createBrowserRouter(routes);
