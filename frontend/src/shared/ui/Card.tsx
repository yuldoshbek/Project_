/**
 * Карточка — единица показа на всех устройствах.
 *
 * У карточки есть заголовок и **вопрос**, на который она отвечает. Это не оформление:
 * показатель без вопроса и без действия запрещён (CLAUDE.md, инвариант 3), и место для
 * вопроса в компоненте — самый дешёвый способ это правило не обойти.
 */

import type { ReactNode } from 'react';

import { cn } from '@/shared/lib/cn';

interface CardProps {
  title: string;
  /** Вопрос руководителя, на который отвечает карточка. */
  question?: string | undefined;
  /** Откуда и когда данные: «по таблице от 15.09». Свежесть показывается всегда. */
  freshness?: string | undefined;
  action?: ReactNode | undefined;
  children: ReactNode;
  className?: string | undefined;
}

export function Card({ title, question, freshness, action, children, className }: CardProps) {
  return (
    <section
      className={cn(
        // min-w-0 — не украшение: у элемента сетки минимальная ширина по умолчанию равна
        // содержимому, и одна длинная строка (например, строка браузера в списке
        // устройств) раздвигает колонку и уносит весь экран в горизонтальную прокрутку.
        'min-w-0 rounded-[var(--radius-lg)] border border-line bg-card shadow-card',
        'p-4 sm:p-5',
        className,
      )}
    >
      {/* На телефоне действие встаёт под заголовком. Рядом кнопка съедает две трети
          ширины, и вопрос карточки печатается столбиком по два слова в строке. */}
      <header className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-ink-strong">{title}</h2>
          {question ? <p className="mt-1 text-sm text-ink-muted">{question}</p> : null}
        </div>
        {action ? <div className="shrink-0 self-start">{action}</div> : null}
      </header>
      {children}
      {freshness ? (
        <p className="mt-4 border-t border-line pt-3 text-xs text-ink-muted">{freshness}</p>
      ) : null}
    </section>
  );
}
