/**
 * Оболочка приложения: то, что остаётся на экране всегда.
 *
 * Раскладок три, потому что у руководителя три разных задачи (см. `app/device.ts`):
 *
 * - **телефон** — одна колонка, навигация внизу под большой палец, заголовок компактный;
 * - **ноутбук** — боковая полоса с подписями, содержимое в одну широкую колонку;
 * - **монитор** — та же полоса, но содержимое шире и с большими промежутками: экран смотрят
 *   с двух метров, а не с шестидесяти сантиметров.
 *
 * Полоса «космоса» сверху — единственное украшение на весь блок 0, и она же несёт смысл:
 * ею отделяется служебная строка состояния от данных. Сцены с частицами на телефоне нет и
 * не будет (ADR-0021 §3а): она стоит секунд загрузки, а решение принимается за полминуты.
 */

import type { ReactNode } from 'react';

import { useDevice } from '@/app/device';
import { cn } from '@/shared/lib/cn';

import { BottomBar } from './BottomBar';
import { SideRail } from './SideRail';
import { TopBar } from './TopBar';

export function AppShell({ children }: { children: ReactNode }) {
  const device = useDevice();
  const isPhone = device === 'phone';

  return (
    <div className="min-h-dvh bg-app text-ink">
      <TopBar device={device} />

      <div className="flex">
        {!isPhone ? <SideRail wide={device === 'monitor'} /> : null}

        <main
          id="main"
          className={
            isPhone
              ? // Отступ снизу — под нижнюю панель и жест-полосу iPhone: без него последняя
                // карточка списка оказывается под кнопками и её не прочитать.
                'min-w-0 flex-1 px-4 pt-4 pb-28 print:p-0'
              : device === 'monitor'
                ? 'min-w-0 flex-1 px-10 py-8 print:p-0'
                : 'min-w-0 flex-1 px-6 py-6 print:p-0'
          }
        >
          <div
            className={cn(
              'mx-auto print:max-w-none',
              device === 'monitor' ? 'max-w-[1600px]' : 'max-w-[1100px]',
            )}
          >
            {children}
          </div>
        </main>
      </div>

      {isPhone ? <BottomBar /> : null}
    </div>
  );
}
