/**
 * Режим «Совещание» — один вопрос на экран (ТЗ 6, критерий 2 блока 3).
 *
 * Повестка — вопросы разделов по порядку; экран закрывает всё приложение: ни боковой панели,
 * ни шапки, ни кнопки захвата. Листается стрелками, пробелом и PageUp/PageDown — пультом
 * презентации, — выход по Esc. Кнопки на экране тихие: их видно, но смотрят не на них.
 */

import { useNavigate } from '@tanstack/react-router';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/shared/lib/cn';
import { Loading } from '@/shared/ui/States';

import { useAgenda } from './useAgenda';

const NEXT = new Set(['ArrowRight', 'ArrowDown', 'PageDown', ' ']);
const PREVIOUS = new Set(['ArrowLeft', 'ArrowUp', 'PageUp']);
const FOCUSABLE = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** Пробел на кнопке нажимает кнопку: листать вместо этого — отнять у неё клавиатуру. */
function isControl(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest('button, a[href], input, textarea') !== null;
}

export default function MeetingMode({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { slides, pending } = useAgenda();
  const dialog = useRef<HTMLDivElement>(null);
  // Кто был в фокусе до совещания — туда фокус и вернётся. Запоминается при первой
  // отрисовке: к эффекту фокус уже внутри диалога.
  const [opener] = useState(() =>
    document.activeElement instanceof HTMLElement ? document.activeElement : null,
  );
  // Позиция — вопрос, а не номер: если повестка изменится под открытым совещанием, экран
  // останется на том же вопросе, а не перескочит на соседний.
  const [current, setCurrent] = useState<string | null>(null);
  const found = slides.findIndex((each) => each.key === current);
  const at = found === -1 ? 0 : found;
  const last = Math.max(0, slides.length - 1);
  // Пока не пришли все разделы — загрузка, а не часть повестки: иначе счётчик меняется с
  // «1 / 2» на «1 / 6» под руками ведущего, а «второй вопрос» сам становится другим.
  const slide = pending ? undefined : slides[at];

  const go = useCallback(
    (step: number) => {
      // Пока повестка грузится, листать нечего: нажатие сдвинуло бы невидимую позицию.
      if (pending) return;
      const next = slides[Math.min(last, Math.max(0, at + step))];
      if (next) setCurrent(next.key);
    },
    [pending, slides, at, last],
  );

  useEffect(() => {
    const node = dialog.current;
    node?.focus();
    return () => {
      // Проверка — на следующем витке: StrictMode снимает и ставит эффекты заново, не убирая
      // диалог. Диалог убран, фокус упал на body — возвращаем на кнопку, которая его открыла.
      setTimeout(() => {
        if (node?.isConnected || !opener?.isConnected) return;
        if (document.activeElement && document.activeElement !== document.body) return;
        opener.focus();
      }, 0);
    };
  }, [opener]);

  useEffect(() => {
    // Tab не уходит за диалог: шапка и боковая панель под ним в документе остаются, и Enter
    // на невидимой ссылке увёл бы в другой раздел (aria-modal).
    const keepInside = (event: KeyboardEvent) => {
      const node = dialog.current;
      if (!node) return;
      const focusable = [...node.querySelectorAll<HTMLElement>(FOCUSABLE)];
      const first = focusable[0];
      const end = focusable.at(-1);
      const active = document.activeElement;
      const inside = active !== node && active instanceof Node && node.contains(active);
      if (!first || !end) {
        event.preventDefault();
        node.focus();
      } else if (!inside) {
        event.preventDefault();
        (event.shiftKey ? end : first).focus();
      } else if (event.shiftKey && active === first) {
        event.preventDefault();
        end.focus();
      } else if (!event.shiftKey && active === end) {
        event.preventDefault();
        first.focus();
      }
    };

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      else if (event.key === 'Tab') keepInside(event);
      else if (event.key === ' ' && isControl(event.target)) return;
      else if (NEXT.has(event.key)) {
        event.preventDefault();
        go(1);
      } else if (PREVIOUS.has(event.key)) {
        event.preventDefault();
        go(-1);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [go, onClose]);

  return (
    <div
      ref={dialog}
      role="dialog"
      aria-modal="true"
      aria-label={t('meeting.label')}
      tabIndex={-1}
      // Рамка фокуса вокруг всего экрана ничего не говорит: фокус на диалоге — чтобы пробел
      // пульта листал, а не нажимал кнопку «Выйти».
      className="fixed inset-0 z-50 flex flex-col bg-app text-ink outline-none"
    >
      {pending ? (
        <div className="grid flex-1 place-items-center">
          <Loading />
        </div>
      ) : slide ? (
        <section
          aria-label={slide.question}
          className="mx-auto flex w-full max-w-[min(90vw,1800px)] flex-1 flex-col justify-center gap-[2.5vh] px-[5vw]"
        >
          <p className="text-[clamp(1rem,1.6vw,2rem)] text-ink-muted">
            {t(`sections.${slide.section}`)}
          </p>
          <h2 className="text-[clamp(1.75rem,3.4vw,4.5rem)] leading-tight font-semibold text-ink-strong">
            {slide.question}
          </h2>
          <p
            className={cn(
              'text-[clamp(2rem,4.4vw,6rem)] leading-tight font-bold',
              slide.failed ? 'text-burn-ink' : slide.empty ? 'text-calm-ink' : 'text-ink-strong',
            )}
          >
            {slide.main}
          </p>
          {slide.detail ? (
            <p className="text-[clamp(1.25rem,2.2vw,3rem)] text-ink">{slide.detail}</p>
          ) : null}
          {slide.lines.length > 0 ? (
            <ul className="flex flex-col gap-[1vh] text-[clamp(1rem,1.7vw,2.25rem)] text-ink">
              {slide.lines.map((line) => (
                <li key={line.key} className="truncate">
                  {line.text}
                </li>
              ))}
            </ul>
          ) : null}
          {slide.freshness ? (
            <p className="text-[clamp(0.875rem,1.2vw,1.5rem)] text-ink-muted">{slide.freshness}</p>
          ) : null}
          <div>
            <button
              type="button"
              onClick={() => {
                onClose();
                void navigate({ to: slide.path });
              }}
              className="min-h-touch rounded-[var(--radius)] px-3 text-[clamp(0.875rem,1.2vw,1.5rem)] text-accent-ink underline-offset-4 hover:underline"
            >
              {t('meeting.open')}
            </button>
          </div>
        </section>
      ) : (
        <p className="grid flex-1 place-items-center text-2xl text-ink-muted">
          {t('meeting.empty')}
        </p>
      )}

      <footer className="flex items-center justify-between gap-4 px-6 pb-5 text-ink-muted">
        <button
          type="button"
          onClick={onClose}
          aria-label={t('meeting.close')}
          className="inline-flex min-h-touch items-center gap-1 rounded-[var(--radius)] px-3 text-sm hover:text-ink"
        >
          <X className="size-4" aria-hidden="true" />
          {t('meeting.closeHint')}
        </button>
        <span className="numeric text-sm" aria-live="polite">
          {slide ? t('meeting.counter', { at: at + 1, total: slides.length }) : null}
        </span>
        <span className="inline-flex gap-1">
          <button
            type="button"
            onClick={() => go(-1)}
            disabled={!slide || at === 0}
            aria-label={t('meeting.previous')}
            className="grid size-11 place-items-center rounded-[var(--radius)] hover:text-ink disabled:opacity-40"
          >
            <ChevronLeft className="size-5" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => go(1)}
            disabled={!slide || at === last}
            aria-label={t('meeting.next')}
            className="grid size-11 place-items-center rounded-[var(--radius)] hover:text-ink disabled:opacity-40"
          >
            <ChevronRight className="size-5" aria-hidden="true" />
          </button>
        </span>
      </footer>
    </div>
  );
}
