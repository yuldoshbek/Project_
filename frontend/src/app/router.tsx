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
import { lazy, Suspense, type ComponentType, type ReactElement } from 'react';

import { IdeasRoute } from '@/sections/ideas/IdeasRoute';
import { IjroRoute } from '@/sections/ijro/IjroRoute';
import { InteractionRoute } from '@/sections/interaction/InteractionRoute';
import { ReportsRoute } from '@/sections/reports/ReportsRoute';
import { PultSection } from '@/sections/pult/PultSection';
import { SoonSection } from '@/sections/SoonSection';
import { RenderFailure } from '@/shared/ui/Boundary';
import { Loading } from '@/shared/ui/States';

/**
 * Раздел отдельным куском. Пульт — в основной сборке: это первый экран руководителя, и
 * ждать второй загрузки ради него нельзя. Остальные грузятся при переходе: на телефоне по
 * 4G каждый лишний килобайт первого экрана — это время исполнения на медленном процессоре
 * (замер первого экрана, критерий 4 блока 3).
 */
function deferred(load: () => Promise<{ default: ComponentType }>): () => ReactElement {
  const Section = lazy(load);
  return function DeferredSection() {
    return (
      <Suspense fallback={<Loading />}>
        <Section />
      </Suspense>
    );
  };
}

const CalendarSection = deferred(() =>
  import('@/sections/calendar/CalendarSection').then((module) => ({
    default: module.CalendarSection,
  })),
);
const ManagementSection = deferred(() =>
  import('@/sections/management/ManagementSection').then((module) => ({
    default: module.ManagementSection,
  })),
);
const ProgramsSection = deferred(() =>
  import('@/sections/programs/ProgramsSection').then((module) => ({
    default: module.ProgramsSection,
  })),
);
const ProjectsSection = deferred(() =>
  import('@/sections/projects/ProjectsSection').then((module) => ({
    default: module.ProjectsSection,
  })),
);
const TasksSection = deferred(() =>
  import('@/sections/tasks/TasksSection').then((module) => ({ default: module.TasksSection })),
);

const rootRoute = createRootRoute({ component: App });

const sectionRoutes: AnyRoute[] = SECTIONS.map((section) =>
  createRoute({
    getParentRoute: () => rootRoute,
    path: sectionPath(section.id),
    component:
      section.id === 'management'
        ? ManagementSection
        : section.id === 'calendar'
          ? CalendarSection
          : section.id === 'pult'
            ? PultSection
            : section.id === 'programs'
              ? ProgramsSection
              : section.id === 'projects'
                ? ProjectsSection
                : section.id === 'tasks'
                  ? TasksSection
                  : section.id === 'ijro'
                    ? IjroRoute
                    : section.id === 'interaction'
                      ? InteractionRoute
                      : section.id === 'reports'
                        ? ReportsRoute
                        : section.id === 'ideas'
                          ? IdeasRoute
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
  // Упавший раздел показывает наше «Не получилось» внутри оболочки: навигация остаётся, и
  // можно уйти в соседний раздел.
  defaultErrorComponent: RenderFailure,
});

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}
