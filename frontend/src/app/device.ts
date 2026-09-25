/**
 * Устройство: телефон, ноутбук, большой монитор.
 *
 * Это не «адаптивность». У руководителя три устройства, и на каждом у него **разная
 * задача**: с телефона — понять за полминуты и решить, на ноутбуке — разобраться, на
 * большом мониторе — провести совещание. Поэтому раскладка не растягивается, а меняется:
 * на телефоне навигация внизу и одна колонка, на ноутбуке боковая полоса и две, на мониторе
 * несколько панелей рядом.
 *
 * Границы выбраны по устройствам заказчика, а не по круглым числам: 390 — iPhone, 1440 —
 * его ноутбук, 2560 — монитор в кабинете.
 */

import { useEffect, useState } from 'react';

export type Device = 'phone' | 'laptop' | 'monitor';

export const PHONE_MAX = 767;
export const MONITOR_MIN = 1800;

export function deviceFor(width: number): Device {
  if (width <= PHONE_MAX) return 'phone';
  if (width >= MONITOR_MIN) return 'monitor';
  return 'laptop';
}

export function useDevice(): Device {
  const [device, setDevice] = useState<Device>(() =>
    typeof window === 'undefined' ? 'laptop' : deviceFor(window.innerWidth),
  );

  useEffect(() => {
    // Слушаем медиа-запросы, а не событие resize: resize срабатывает на каждый пиксель
    // при перетаскивании окна, и перерисовка оболочки идёт сотни раз вместо двух.
    const phone = window.matchMedia(`(max-width: ${PHONE_MAX}px)`);
    const monitor = window.matchMedia(`(min-width: ${MONITOR_MIN}px)`);
    const decide = () => setDevice(deviceFor(window.innerWidth));

    phone.addEventListener('change', decide);
    monitor.addEventListener('change', decide);
    decide();

    return () => {
      phone.removeEventListener('change', decide);
      monitor.removeEventListener('change', decide);
    };
  }, []);

  return device;
}
