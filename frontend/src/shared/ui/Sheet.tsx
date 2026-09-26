/**
 * Лист поверх экрана: на телефоне — во весь экран, на ноутбуке и мониторе — панель справа.
 *
 * Своё, а не библиотека диалогов: нужно ровно три свойства — закрыть по Escape, по щелчку
 * мимо и по кнопке, и поставить фокус внутрь при открытии. Тянуть ради них пакет с десятком
 * компонентов запрещено (CLAUDE.md, «Чего не делать»).
 */

import { X } from 'lucide-react';
import { useEffect, useRef, type ReactNode } from 'react';

import { cn } from '@/shared/lib/cn';

interface SheetProps {
  label: string;
  closeLabel: string;
  onClose: () => void;
  children: ReactNode;
  /** Ширина панели на ноутбуке и мониторе. */
  wide?: boolean;
}

export function Sheet({ label, closeLabel, onClose, children, wide = false }: SheetProps) {
  const close = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    close.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end print:hidden">
      <div className="absolute inset-0 bg-ink-strong/30" onClick={onClose} aria-hidden="true" />
      <section
        role="dialog"
        aria-modal="true"
        aria-label={label}
        className={cn(
          'relative flex h-full w-full flex-col overflow-y-auto bg-app shadow-raised',
          'md:border-l md:border-line',
          wide ? 'md:max-w-[44rem]' : 'md:max-w-[34rem]',
        )}
      >
        <div className="sticky top-0 z-10 flex justify-end bg-app/95 px-2 pt-[env(safe-area-inset-top)] backdrop-blur">
          {/* Обычная кнопка, а не `Button`: фокус ставится на неё при открытии, а `Button`
              ссылку на элемент наружу не отдаёт. Вид — тот же «тихий». */}
          <button
            ref={close}
            type="button"
            onClick={onClose}
            aria-label={closeLabel}
            className="grid min-h-touch min-w-touch place-items-center rounded-[var(--radius)] text-ink-muted hover:bg-hover hover:text-ink"
          >
            <X className="size-5" aria-hidden="true" />
          </button>
        </div>
        <div className="flex flex-col gap-4 px-4 pb-[calc(env(safe-area-inset-bottom)+1.5rem)] sm:px-6">
          {children}
        </div>
      </section>
    </div>
  );
}
