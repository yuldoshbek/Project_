/**
 * Рамка блока карточки проекта: заголовок, вопрос, справа — короткая сводка или действие.
 *
 * Вопрос — не украшение: у каждого показателя есть вопрос руководителя (инвариант 3).
 */

import type { ReactNode } from 'react';

interface BlockProps {
  title: string;
  question?: string;
  aside?: ReactNode;
  children: ReactNode;
}

export function Block({ title, question, aside, children }: BlockProps) {
  return (
    <section className="rounded-[var(--radius-lg)] border border-line bg-card p-4">
      <header className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-ink-strong">{title}</h3>
          {question ? <p className="text-xs text-ink-muted">{question}</p> : null}
        </div>
        {aside ? <div className="numeric shrink-0 text-xs text-ink-muted">{aside}</div> : null}
      </header>
      {children}
    </section>
  );
}
