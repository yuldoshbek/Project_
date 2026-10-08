/**
 * Маршрут раздела «Ижро» — первый раздел, который грузится отдельным куском.
 *
 * До блока 2 начальный JS занимал 207 КБ из бюджета 250 (`scripts/check-budget.mjs`): трём
 * разделам блока с загрузкой файлов в оставшиеся 43 КБ не поместиться, а Пульт на телефоне
 * руководителя от них тяжелеть не должен. Раздел приезжает по первому заходу в него.
 */

import { lazy, Suspense } from 'react';

import { Loading } from '@/shared/ui/States';

const IjroSection = lazy(() =>
  import('./IjroSection').then((module) => ({ default: module.IjroSection })),
);

export function IjroRoute() {
  return (
    <Suspense fallback={<Loading />}>
      <IjroSection />
    </Suspense>
  );
}
