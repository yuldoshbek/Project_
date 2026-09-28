/**
 * Лист поверх экрана: на телефоне — во весь экран, на ноутбуке и мониторе — панель справа.
 *
 * Своё, а не библиотека диалогов: нужно ровно несколько свойств — закрыть по Escape, по
 * щелчку мимо и по кнопке; поставить фокус внутрь при открытии; держать Tab внутри, пока
 * лист открыт, и вернуть фокус туда, откуда лист открыли. Тянуть ради них пакет с десятком
 * компонентов запрещено (CLAUDE.md, «Чего не делать»).
 */

import { X } from 'lucide-react';
import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';

import { cn } from '@/shared/lib/cn';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

interface SheetProps {
  label: string;
  closeLabel: string;
  onClose: () => void;
  children: ReactNode;
  /** Ширина панели на ноутбуке и мониторе. */
  wide?: boolean;
  /**
   * Фокус — на кнопку «закрыть» при открытии. Выключается там, где лист открывают ради
   * ввода (Захват): фокус сразу в поле, на телефоне сразу клавиатура.
   */
  focusClose?: boolean;
}

export function Sheet({
  label,
  closeLabel,
  onClose,
  children,
  wide = false,
  focusClose = true,
}: SheetProps) {
  const close = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);
  // Кто был в фокусе до листа — запоминается при первой отрисовке: к эффекту фокус уже
  // внутри (autoFocus поля Захвата срабатывает раньше эффектов).
  const [opener] = useState(() =>
    document.activeElement instanceof HTMLElement ? document.activeElement : null,
  );

  useEffect(() => {
    const node = panel.current;
    return () => {
      // Проверка — на следующем витке: StrictMode снимает и ставит эффекты заново, не
      // убирая лист, и фокус не должен уехать из поля. Лист убран, фокус упал на body —
      // возвращаем на кнопку, которая лист открыла.
      setTimeout(() => {
        if (node?.isConnected || !opener?.isConnected) return;
        if (document.activeElement && document.activeElement !== document.body) return;
        opener.focus();
      }, 0);
    };
  }, [opener]);

  // Tab с последнего поля — на первое, Shift+Tab с первого — на последнее: за листом
  // экран, до которого с открытым листом дотянуться нельзя (aria-modal).
  const keepInside = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key !== 'Tab' || !panel.current) return;
    const focusable = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
    const first = focusable[0];
    const last = focusable.at(-1);
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  useEffect(() => {
    if (focusClose) close.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, focusClose]);

  return (
    <div className="fixed inset-0 z-50 flex justify-end print:hidden">
      <div className="absolute inset-0 bg-ink-strong/30" onClick={onClose} aria-hidden="true" />
      <section
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        onKeyDown={keepInside}
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
