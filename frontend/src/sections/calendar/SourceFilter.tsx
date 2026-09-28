/**
 * Что показывать: пять источников дат блока 1. Остальные источники названы строкой ниже —
 * календарь без поручений Ижро иначе читался бы как «поручений нет», а их просто ещё не
 * привезли (блок 2).
 */

import { useTranslation } from 'react-i18next';

import { cn } from '@/shared/lib/cn';

import { KIND_ICON } from './kinds';
import { KINDS, type ItemKind } from './model';

interface SourceFilterProps {
  shown: ReadonlySet<ItemKind>;
  onToggle: (kind: ItemKind) => void;
}

export function SourceFilter({ shown, onToggle }: SourceFilterProps) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-1.5">
      <div role="group" aria-label={t('calendar.sources.label')} className="flex flex-wrap gap-2">
        {KINDS.map((kind) => {
          const Icon = KIND_ICON[kind];
          const on = shown.has(kind);
          return (
            <button
              key={kind}
              type="button"
              aria-pressed={on}
              onClick={() => onToggle(kind)}
              className={cn(
                'inline-flex min-h-touch items-center gap-1.5 rounded-[var(--radius-pill)] border px-3 text-sm md:min-h-9',
                'transition-colors duration-[var(--motion-fast)]',
                on
                  ? 'border-line-accent bg-accent-soft text-accent-ink'
                  : 'border-line bg-card text-ink-muted hover:bg-hover',
              )}
            >
              <Icon className="size-4" aria-hidden="true" />
              {t(`calendar.filter.${kind}`)}
            </button>
          );
        })}
      </div>
      <p className="text-xs text-ink-muted">{t('calendar.sources.later')}</p>
    </div>
  );
}
