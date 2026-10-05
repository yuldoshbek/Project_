/**
 * Режим «Совещание» — один вопрос на экран (ТЗ 6, критерий 2 блока 3).
 *
 * Повестка — вопросы разделов по порядку; экран закрывает всё приложение: ни боковой панели,
 * ни шапки, ни кнопки захвата. Листается стрелками, пробелом и PageUp/PageDown — пультом
 * презентации, — выход по Esc. Кнопки на экране тихие: их видно, но смотрят не на них.
 */

import { useNavigate } from '@tanstack/react-router';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Loading } from '@/shared/ui/States';

import { useAgenda } from './useAgenda';

const NEXT = new Set(['ArrowRight', 'ArrowDown', 'PageDown', ' ']);
const PREVIOUS = new Set(['ArrowLeft', 'ArrowUp', 'PageUp']);

export default function MeetingMode({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { slides, pending } = useAgenda();
  const [index, setIndex] = useState(0);
  const last = Math.max(0, slides.length - 1);
  const at = Math.min(index, last);
  const slide = slides[at];

  const go = useCallback(
    (step: number) => setIndex((current) => Math.min(last, Math.max(0, current + step))),
    [last],
  );

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
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
      role="dialog"
      aria-modal="true"
      aria-label={t('meeting.label')}
      className="fixed inset-0 z-50 flex flex-col bg-app text-ink"
    >
      {pending && !slide ? (
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
            className={
              slide.empty
                ? 'text-[clamp(2rem,4.4vw,6rem)] leading-tight font-bold text-calm-ink'
                : 'text-[clamp(2rem,4.4vw,6rem)] leading-tight font-bold text-ink-strong'
            }
          >
            {slide.main}
          </p>
          {slide.detail ? (
            <p className="text-[clamp(1.25rem,2.2vw,3rem)] text-ink">{slide.detail}</p>
          ) : null}
          {slide.lines.length > 0 ? (
            <ul className="flex flex-col gap-[1vh] text-[clamp(1rem,1.7vw,2.25rem)] text-ink">
              {slide.lines.map((line) => (
                <li key={line} className="truncate">
                  {line}
                </li>
              ))}
            </ul>
          ) : null}
          <p className="text-[clamp(0.875rem,1.2vw,1.5rem)] text-ink-muted">{slide.freshness}</p>
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
          {slides.length > 0 ? t('meeting.counter', { at: at + 1, total: slides.length }) : null}
        </span>
        <span className="inline-flex gap-1">
          <button
            type="button"
            onClick={() => go(-1)}
            disabled={at === 0}
            aria-label={t('meeting.previous')}
            className="grid size-11 place-items-center rounded-[var(--radius)] hover:text-ink disabled:opacity-40"
          >
            <ChevronLeft className="size-5" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => go(1)}
            disabled={at === last}
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
