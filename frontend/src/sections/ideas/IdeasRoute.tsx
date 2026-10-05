/**
 * Маршрут раздела «Идеи и карты» — отдельным куском, как разделы блока 2: полотно карты не
 * утяжеляет Пульт на телефоне руководителя.
 */

import { lazy, Suspense } from 'react';

import { Loading } from '@/shared/ui/States';

const IdeasSection = lazy(() =>
  import('./IdeasSection').then((module) => ({ default: module.IdeasSection })),
);

export function IdeasRoute() {
  return (
    <Suspense fallback={<Loading />}>
      <IdeasSection />
    </Suspense>
  );
}
