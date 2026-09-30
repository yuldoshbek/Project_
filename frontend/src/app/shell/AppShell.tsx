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
 * верхней строке, посередине нижней панели телефона и клавишей «+» на ноутбуке.
 *
 * Полоса «космоса» сверху — единственное украшение на весь блок 0, и она же несёт смысл:
 * ею отделяется служебная строка состояния от данных. Сцены с частицами на телефоне нет и
 * не будет (ADR-0021 §3а): она стоит секунд загрузки, а решение принимается за полминуты.
 */

import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { useDevice } from '@/app/device';
import { CaptureForm } from '@/sections/capture/CaptureForm';
import { cn } from '@/shared/lib/cn';
import { Sheet } from '@/shared/ui/Sheet';

import { BottomBar } from './BottomBar';
import { SideRail } from './SideRail';
import { TopBar } from './TopBar';

/** Клавиша «+» — не посреди набора текста: там это просто плюс. */
function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);
}

export function AppShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const device = useDevice();
  const isPhone = device === 'phone';
  const [capturing, setCapturing] = useState(false);
  const openCapture = useCallback(() => setCapturing(true), []);
  const closeCapture = useCallback(() => setCapturing(false), []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== '+' || event.ctrlKey || event.metaKey || event.altKey) return;
      if (isTyping(event.target) || document.querySelector('[role="dialog"]')) return;
      event.preventDefault();
      setCapturing(true);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div className="min-h-dvh bg-app text-ink">
      <TopBar device={device} onCapture={openCapture} />

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

      {isPhone ? <BottomBar onCapture={openCapture} /> : null}

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
    </div>
  );
}
