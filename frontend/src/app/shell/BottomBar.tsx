/**
 * Нижняя панель — телефон: «Пульт · Календарь · (+) · Поиск · Ещё» (ТЗ 6).
 *
 * Внизу, а не вверху: систему открывают одной рукой на ходу, и верх экрана iPhone большим
 * пальцем не достаётся. Пять мест — предел: шестая кнопка на 390 px делает цель нажатия
 * меньше 44 px, то есть превращает навигацию в промахи. Захват — посередине и крупнее: это
 * главное, что помощник делает с телефона (ТЗ 6), и он есть на каждом экране (ТЗ 7).
 * Остальные разделы — в «Ещё».
 *
 * Отступ снизу берётся из `env(safe-area-inset-bottom)`: без него панель уезжает под
 * жест-полосу, и нижний ряд кнопок не нажимается вовсе.
 */

import { Link, useRouterState } from '@tanstack/react-router';
import { Menu, Plus, Search } from 'lucide-react';
import { useCallback, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { MORE_SECTIONS, PHONE_SECTIONS, sectionPath } from '@/app/sections';
import { cn } from '@/shared/lib/cn';
import { Sheet } from '@/shared/ui/Sheet';

const SLOT =
  'flex min-h-touch w-full flex-col items-center justify-center gap-1 px-1 py-2 text-[11px] transition-colors duration-[var(--motion-fast)]';

export function BottomBar({
  onCapture,
  onSearch,
}: {
  onCapture: () => void;
  onSearch: () => void;
}) {
  const { t } = useTranslation();
  const path = useRouterState({ select: (state) => state.location.pathname });
  const [sheet, setSheet] = useState<'more' | null>(null);
  const close = useCallback(() => setSheet(null), []);
  const isActive = (to: string) => (to === '/' ? path === '/' : path.startsWith(to));
  const inMore = MORE_SECTIONS.some((section) => isActive(sectionPath(section.id)));

  const link = (id: string, icon: ReactNode) => {
    const to = sectionPath(id);
    const active = isActive(to);
    return (
      <Link
        to={to}
        aria-current={active ? 'page' : undefined}
        className={cn(SLOT, active ? 'text-accent' : 'text-ink-muted')}
      >
        {icon}
        <span className="truncate">{t(`sections.${id}`)}</span>
      </Link>
    );
  };

  const [pult, calendar] = PHONE_SECTIONS;
  const PultIcon = pult!.icon;
  const CalendarIcon = calendar!.icon;

  return (
    <>
      <nav
        aria-label={t('app.name')}
        className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-card print:hidden"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        <ul className="flex items-end">
          <li className="flex-1">{link(pult!.id, <PultIcon className="size-5" />)}</li>
          <li className="flex-1">{link(calendar!.id, <CalendarIcon className="size-5" />)}</li>
          <li className="flex flex-1 justify-center">
            <button
              type="button"
              onClick={onCapture}
              aria-label={t('capture.open')}
              className="-mt-4 mb-1 grid size-14 place-items-center rounded-full bg-accent text-ink-inverse shadow-raised transition-colors duration-[var(--motion-fast)] hover:bg-accent-hover"
            >
              <Plus className="size-7" aria-hidden="true" />
            </button>
          </li>
          <li className="flex-1">
            <button type="button" onClick={onSearch} className={cn(SLOT, 'text-ink-muted')}>
              <Search className="size-5" aria-hidden="true" />
              <span className="truncate">{t('app.search')}</span>
            </button>
          </li>
          <li className="flex-1">
            <button
              type="button"
              onClick={() => setSheet('more')}
              aria-current={inMore ? 'page' : undefined}
              className={cn(SLOT, inMore ? 'text-accent' : 'text-ink-muted')}
            >
              <Menu className="size-5" aria-hidden="true" />
              <span className="truncate">{t('app.more')}</span>
            </button>
          </li>
        </ul>
      </nav>

      {sheet === 'more' ? (
        <Sheet label={t('app.moreTitle')} closeLabel={t('app.moreClose')} onClose={close}>
          <h2 className="text-lg font-semibold text-ink-strong">{t('app.moreTitle')}</h2>
          <ul className="flex flex-col gap-1">
            {MORE_SECTIONS.map((section) => {
              const to = sectionPath(section.id);
              const Icon = section.icon;
              return (
                <li key={section.id}>
                  <Link
                    to={to}
                    onClick={close}
                    aria-current={isActive(to) ? 'page' : undefined}
                    className={cn(
                      'flex min-h-touch items-center gap-3 rounded-[var(--radius)] px-3 text-[15px]',
                      isActive(to) ? 'bg-accent-soft text-accent-ink' : 'text-ink hover:bg-hover',
                    )}
                  >
                    <Icon className="size-5 shrink-0" />
                    <span className="min-w-0 flex-1 truncate">{t(`sections.${section.id}`)}</span>
                    {!section.ready ? (
                      <span className="text-xs text-ink-muted">
                        {t('app.moreSoon', { block: section.block })}
                      </span>
                    ) : null}
                  </Link>
                </li>
              );
            })}
          </ul>
        </Sheet>
      ) : null}
    </>
  );
}
