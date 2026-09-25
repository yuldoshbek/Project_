/**
 * Отказ при отрисовке — тем же состоянием «Не получилось», что и отказ запроса.
 *
 * Два уровня. Карточка, упавшая при отрисовке, показывает отказ на своём месте, а соседние
 * продолжают работать: ответ, разошедшийся с типом, не должен гасить раздел целиком — так
 * «Управление» падало полностью, когда бэкенд перестал отдавать приоритеты. Раздел, упавший
 * целиком, получает то же состояние от маршрутизатора вместо его английского «Something went
 * wrong!».
 */

import { CatchBoundary, type ErrorComponentProps } from '@tanstack/react-router';
import type { ReactNode } from 'react';

import { describeError } from '@/shared/api/client';

import { Card } from './Card';
import { Failure } from './States';

/** Обработчик ошибок маршрута: `defaultErrorComponent` маршрутизатора. */
export function RenderFailure({ error, reset }: ErrorComponentProps) {
  return <Failure kind="render" detail={describeError(error)} onRetry={reset} />;
}

/** Граница одной карточки: отказ рисуется в карточке с тем же заголовком. */
export function CardBoundary({ title, children }: { title: string; children: ReactNode }) {
  return (
    <CatchBoundary
      getResetKey={() => title}
      errorComponent={function CardFailure(props: ErrorComponentProps) {
        return (
          <Card title={title}>
            <RenderFailure {...props} />
          </Card>
        );
      }}
    >
      {children}
    </CatchBoundary>
  );
}
