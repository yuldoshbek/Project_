/**
 * Маршруты — по одному на раздел ТЗ, из одного списка `app/sections.ts`.
 *
 * Маршруты описаны кодом, а не файлами: разделов десять, они заданы требованиями и не
 * меняются от правки к правке, а генерация дерева по файлам добавила бы шаг сборки и
 * сгенерированный файл в репозиторий ради той же таблицы.
 *
 * Раздел, у которого ещё нет данных, ведёт на `SoonSection` с его вопросом и номером блока.
 * Так ссылка никогда не приводит на пустой экран — это ровно та поломка, которую нельзя
 * отличить от забытого раздела.
 */

import {
  createRootRoute,
  createRoute,
  createRouter,
  Navigate,
  type AnyRoute,
} from '@tanstack/react-router';

import { App } from '@/app/App';
import { SECTIONS, sectionPath } from '@/app/sections';
import { ManagementSection } from '@/sections/management/ManagementSection';
import { SoonSection } from '@/sections/SoonSection';

const rootRoute = createRootRoute({ component: App });

const sectionRoutes: AnyRoute[] = SECTIONS.map((section) =>
  createRoute({
    getParentRoute: () => rootRoute,
    path: sectionPath(section.id),
    component:
      section.id === 'management'
        ? ManagementSection
        : function Section() {
            return <SoonSection section={section} />;
          },
  }),
);

// Неизвестный адрес уводит на Пульт, а не показывает «страница не найдена»: пользователей
// двое, ссылок снаружи нет, и единственный источник неверного адреса — опечатка в строке.
const notFoundRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '*',
  component: function NotFound() {
    return <Navigate to="/" replace />;
  },
});

export const router = createRouter({
  routeTree: rootRoute.addChildren([...sectionRoutes, notFoundRoute]),
  defaultPreload: 'intent',
});

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
