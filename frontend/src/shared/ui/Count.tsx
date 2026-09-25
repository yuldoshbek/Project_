/**
 * Число, которое вспыхивает, когда меняется.
 *
 * «Одна вспышка изменившегося числа» — это и есть живое время ORBITA (ADR-0034, ТЗ 6):
 * опрос приносит новое значение, и глаз замечает, что именно поменялось, не сравнивая
 * экран с памятью. Вспышка — только при изменении, не при первом показе: иначе при каждом
 * открытии экрана мигало бы всё сразу, и сигнал превратился бы в шум.
 */

import { useEffect, useRef, useState } from 'react';

import { cn } from '@/shared/lib/cn';

export function Count({ value, className }: { value: number; className?: string }) {
  const previous = useRef(value);
  const [flashes, setFlashes] = useState(0);

  useEffect(() => {
    if (previous.current !== value) {
      previous.current = value;
      setFlashes((count) => count + 1);
    }
  }, [value]);

  return (
    <span
      // Новый ключ перезапускает анимацию: два изменения подряд дают две вспышки.
      key={flashes}
      className={cn(
        'numeric inline-block rounded-[var(--radius-sm)]',
        flashes > 0 && 'animate-flash',
        className,
      )}
    >
      {value}
    </span>
  );
}
