/**
 * Нижняя панель — телефон.
 *
 * Внизу, а не вверху: систему открывают одной рукой на ходу, и верх экрана iPhone большим
 * пальцем не достаётся. Пять разделов — предел: шестая кнопка на 390 px делает цель нажатия
 * меньше 44 px, то есть превращает навигацию в промахи.
 *
 * Отступ снизу берётся из `env(safe-area-inset-bottom)`: без него панель уезжает под
 * жест-полосу, и нижний ряд кнопок не нажимается вовсе.
 */

import { Link, useRouterState } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { PHONE_SECTIONS, sectionPath } from '@/app/sections';
import { cn } from '@/shared/lib/cn';

export function BottomBar() {
  const { t } = useTranslation();
  const path = useRouterState({ select: (state) => state.location.pathname });

  return (
    <nav
      aria-label={t('app.name')}
      className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-card print:hidden"
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      <ul className="flex">
        {PHONE_SECTIONS.map((section) => {
          const to = sectionPath(section.id);
          const active = to === '/' ? path === '/' : path.startsWith(to);
          const Icon = section.icon;

          return (
            <li key={section.id} className="flex-1">
              <Link
                to={to}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'flex min-h-touch flex-col items-center justify-center gap-1 px-1 py-2',
                  'text-[11px] transition-colors duration-[var(--motion-fast)]',
                  active ? 'text-accent' : 'text-ink-muted',
                )}
              >
                <Icon className="size-5" />
                <span className="truncate">{t(`sections.${section.id}`)}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
