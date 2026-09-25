/**
 * Боковая полоса разделов — ноутбук и монитор.
 *
 * Подписи есть всегда: полоса из одних значков экономит сорок пикселей и стоит секунды
 * узнавания на каждом переходе. У неготовых разделов стоит номер блока — так видно, что
 * это план, а не поломка.
 */

import { Link, useRouterState } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { SECTIONS, sectionPath } from '@/app/sections';
import { cn } from '@/shared/lib/cn';

export function SideRail({ wide }: { wide: boolean }) {
  const { t } = useTranslation();
  const path = useRouterState({ select: (state) => state.location.pathname });

  return (
    <nav
      aria-label={t('app.name')}
      className={cn(
        // Прилипает под верхней строкой: высота строки — токен, а не число здесь.
        'sticky top-topbar h-[calc(100dvh-var(--topbar-height))] shrink-0 overflow-y-auto',
        'border-r border-line bg-card px-2 py-3',
        wide ? 'w-64' : 'w-56',
      )}
    >
      <ul className="flex flex-col gap-0.5">
        {SECTIONS.map((section) => {
          const to = sectionPath(section.id);
          const active = to === '/' ? path === '/' : path.startsWith(to);
          const Icon = section.icon;

          return (
            <li key={section.id}>
              <Link
                to={to}
                // Цифра блока рядом с названием читалась как счётчик записей. Готовность
                // показывается иначе: неготовый раздел приглушён, а когда он появится —
                // написано в подсказке.
                title={section.block > 0 ? t('soon.title', { block: section.block }) : undefined}
                className={cn(
                  'flex min-h-10 items-center gap-2.5 rounded-[var(--radius)] px-3 text-sm',
                  'transition-colors duration-[var(--motion-fast)]',
                  active
                    ? 'bg-accent-soft font-medium text-accent-ink'
                    : section.block > 0
                      ? 'text-ink-muted hover:bg-hover'
                      : 'text-ink hover:bg-hover',
                )}
              >
                <Icon className="size-4 shrink-0" />
                <span className="truncate">{t(`sections.${section.id}`)}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
