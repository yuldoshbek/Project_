/**
 * Маршрут раздела «Взаимодействие» — отдельным куском, как «Ижро» (`IjroRoute.tsx`):
 * разделы блока 2 не утяжеляют Пульт на телефоне руководителя.
 */

import { lazy, Suspense } from 'react';

import { Loading } from '@/shared/ui/States';

const InteractionSection = lazy(() =>
  import('./InteractionSection').then((module) => ({ default: module.InteractionSection })),
);

export function InteractionRoute() {
  return (
    <Suspense fallback={<Loading />}>
      <InteractionSection />
    </Suspense>
  );
}
