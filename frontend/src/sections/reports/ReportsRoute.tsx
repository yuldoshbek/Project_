/**
 * Маршрут раздела «Доклады и мероприятия» — отдельным куском, как «Ижро» и «Взаимодействие»:
 * разделы блока 2 не утяжеляют Пульт на телефоне руководителя.
 */

import { lazy, Suspense } from 'react';

import { Loading } from '@/shared/ui/States';

const ReportsSection = lazy(() =>
  import('./ReportsSection').then((module) => ({ default: module.ReportsSection })),
);

export function ReportsRoute() {
  return (
    <Suspense fallback={<Loading />}>
      <ReportsSection />
    </Suspense>
  );
}
