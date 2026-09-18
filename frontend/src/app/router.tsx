import type { RouteObject } from 'react-router-dom';
import { createBrowserRouter } from 'react-router-dom';

import { ProjectCardPage } from '../features/projects/ProjectCardPage';
import { EditProjectPage, NewProjectPage } from '../features/projects/ProjectFormPage';
import { ProjectsPage } from '../features/projects/ProjectsPage';
import { TasksPage } from '../features/tasks/TasksPage';
import { AppLayout } from '../layout/AppLayout';
import { ForbiddenPage } from '../pages/ForbiddenPage';
import { NotFoundPage } from '../pages/NotFoundPage';
import { PlaceholderPage } from '../pages/PlaceholderPage';
import { NAV_ITEMS, ROUTES } from './routes';

/** Готовые экраны по адресу. Заглушка остаётся там, где экрана ещё нет. */
const SCREENS: Record<string, React.ReactElement> = {
  [ROUTES.projects]: <ProjectsPage />,
  [ROUTES.tasks]: <TasksPage />,
};

/**
 * Маршруты приложения.
 *
 * Разделы собираются из `NAV_ITEMS`: меню и маршруты обязаны совпадать, а два списка
 * рано или поздно расходятся. По мере готовности экранов `PlaceholderPage` заменяется
 * настоящим компонентом — построчно, по одному тикету.
 */
export const routes: RouteObject[] = [
  // Ворот больше нет: входа в системе не существует (ADR-0026), и приложение
  // открывается сразу. Кого до него допускать, решает периметр, а не маршрутизатор.
  {
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
          // Экраны портфеля, которых нет в меню: на них приводят из списка и из
          // карточки, а не из бокового меню. Собираются не из `NAV_ITEMS` именно
          // поэтому — пункт меню «Новый проект» был бы разделом, которым он не является.
          { path: ROUTES.projectNew.slice(1), element: <NewProjectPage /> },
          { path: ROUTES.projectEdit.slice(1), element: <EditProjectPage /> },
          { path: ROUTES.projectCard.slice(1), element: <ProjectCardPage /> },
          { path: ROUTES.forbidden.slice(1), element: <ForbiddenPage /> },
          { path: '*', element: <NotFoundPage /> },
        ],
      },
    ],
  },
];

export const router = createBrowserRouter(routes);
