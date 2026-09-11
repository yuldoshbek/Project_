/**
 * Значки разделов.
 *
 * Штриховые, на сетке 24, толщина 1.5 — как в эталонном листе дизайн-системы
 * (`design/Icons.dc.html`). Цвет берётся от текста (`currentColor`): значок в нижней
 * панели обязан менять цвет вместе с подписью, иначе активный раздел выглядит
 * наполовину активным.
 *
 * Рисуются разметкой, а не подключается библиотека: семь значков не стоят зависимости,
 * которую придётся обновлять и в которой придётся искать нужное (CLAUDE.md: не тянуть
 * библиотеку целиком ради одного компонента).
 */

import type { ReactElement } from 'react';

const BASE = {
  width: 22,
  height: 22,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.5,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
  focusable: false,
};

/** Значки по ключу пункта меню. Ключ тот же, что у подписи, — списки не разойдутся. */
export const SECTION_ICONS: Record<string, ReactElement> = {
  'nav.dashboard': (
    <svg {...BASE}>
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </svg>
  ),
  'nav.today': (
    <svg {...BASE}>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </svg>
  ),
  'nav.projects': (
    <svg {...BASE}>
      <path d="M3 7.5A1.5 1.5 0 0 1 4.5 6h4l2 2.5h7A1.5 1.5 0 0 1 19 10v7.5a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 3 17.5z" />
    </svg>
  ),
  'nav.tasks': (
    <svg {...BASE}>
      <path d="M4 7.5 5.8 9.5 9 6" />
      <path d="M4 16.5 5.8 18.5 9 15" />
      <path d="M12 8h8M12 17h8" />
    </svg>
  ),
  'nav.calendar': (
    <svg {...BASE}>
      <rect x="3.5" y="5" width="17" height="15" rx="2" />
      <path d="M3.5 9.5h17M8 3.5V6M16 3.5V6" />
    </svg>
  ),
  'nav.reports': (
    <svg {...BASE}>
      <path d="M6.5 3.5h7L18 8v12.5H6.5z" />
      <path d="M13.5 3.5V8H18" />
      <path d="M9.5 13h5M9.5 16.5h5" />
    </svg>
  ),
  'nav.admin': (
    <svg {...BASE}>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3.5v2.2M12 18.3v2.2M20.5 12h-2.2M5.7 12H3.5M18 6l-1.6 1.6M7.6 16.4 6 18M18 18l-1.6-1.6M7.6 7.6 6 6" />
    </svg>
  ),
};
