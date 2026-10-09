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
 * Захват живёт здесь, а не в разделах: он есть на каждом экране (ТЗ 6, 7) — кнопкой в
 * верхней строке, посередине нижней панели телефона и клавишей «+» на ноутбуке. Поиск —
 * так же: в нижней панели телефона, кнопкой в верхней строке и клавишей «/» или Ctrl+K.
 * Панель поиска грузится отдельным куском при первом открытии: первый экран телефона её
 * не ждёт (замер первого экрана, критерий 4 блока 3).
 *
 * Полоса «космоса» сверху — единственное украшение на весь блок 0, и она же несёт смысл:
 * ею отделяется служебная строка состояния от данных. Сцены с частицами на телефоне нет и
 * не будет (ADR-0021 §3а): она стоит секунд загрузки, а решение принимается за полминуты.
 */

import { useRouterState } from '@tanstack/react-router';
import { lazy, Suspense, useCallback, useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { useDevice } from '@/app/device';
import { CaptureForm } from '@/sections/capture/CaptureForm';
import { cn } from '@/shared/lib/cn';
import { Sheet } from '@/shared/ui/Sheet';

import { BottomBar } from './BottomBar';
import { SideRail } from './SideRail';
import { TopBar } from './TopBar';

const SearchPanel = lazy(() => import('@/sections/search/SearchPanel'));

/** Клавиша «+» — не посреди набора текста: там это просто плюс. */
function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);
}

export function AppShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const device = useDevice();
  const isPhone = device === 'phone';
  // Раздел — маршрут, который уже нарисован, а не адрес: адрес роутер меняет сразу по
  // касанию, а новый маршрут приходит в Outlet позже. Ключ по адресу размонтировал бы и
  // заново смонтировал уходящий раздел (лишние запросы, анимация не на том разделе).
  // Маршрут читается из того же списка, по которому Outlet выбирает раздел.
  const section = useRouterState({
    // Тип — явно: маршруты разделов собраны списком (AnyRoute), и без него routeId — any.
    select: (state): string | undefined => state.matches.at(-1)?.routeId,
  });
  const [capturing, setCapturing] = useState(false);
  const openCapture = useCallback(() => setCapturing(true), []);
  const closeCapture = useCallback(() => setCapturing(false), []);
  const [searching, setSearching] = useState(false);
  const openSearch = useCallback(() => setSearching(true), []);
  const closeSearch = useCallback(() => setSearching(false), []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (document.querySelector('[role="dialog"]')) return;
      // Ctrl+K (⌘K) — привычное сочетание поиска, работает и посреди набора текста.
      const searchKey = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k';
      if (searchKey || (event.key === '/' && !isTyping(event.target))) {
        event.preventDefault();
        setSearching(true);
        return;
      }
      if (event.key !== '+' || event.ctrlKey || event.metaKey || event.altKey) return;
      if (isTyping(event.target)) return;
      event.preventDefault();
      setCapturing(true);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div className="min-h-dvh bg-app text-ink">
      <TopBar device={device} onCapture={openCapture} onSearch={openSearch} />

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
            {/* Ключ — раздел: при переходе он появляется плавно, а не вспыхивает целиком. */}
            <div key={section} className="animate-enter">
              {children}
            </div>
          </div>
        </main>
      </div>

      {isPhone ? <BottomBar onCapture={openCapture} onSearch={openSearch} /> : null}

      {capturing ? (
        <Sheet
          label={t('capture.title')}
          closeLabel={t('capture.close')}
          onClose={closeCapture}
          focusClose={false}
        >
          <CaptureForm />
        </Sheet>
      ) : null}

      {searching ? (
        <Sheet
          label={t('search.title')}
          closeLabel={t('search.close')}
          onClose={closeSearch}
          focusClose={false}
        >
          <Suspense fallback={null}>
            <SearchPanel onPick={closeSearch} />
          </Suspense>
        </Sheet>
      ) : null}
    </div>
  );
}
