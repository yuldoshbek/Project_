/**
 * Адреса экранов и состав бокового меню.
 *
 * Состав повторяет раздел 9 ТЗ. Ссылки на экраны собираются отсюда, а не пишутся
 * строками по месту: иначе при переименовании адреса часть переходов тихо ломается.
 */

export const ROUTES = {
  dashboard: '/',
  today: '/today',
  projects: '/projects',
  tasks: '/tasks',
  calendar: '/calendar',
  reports: '/reports',
  admin: '/admin',
  forbidden: '/403',
} as const;

export interface NavItem {
  to: string;
  labelKey: string;
  /** Тикет, в котором появится содержимое экрана. */
  ticket: string;
  /** Точное совпадение адреса — нужно для корневого пункта. */
  end?: boolean;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { to: ROUTES.dashboard, labelKey: 'nav.dashboard', ticket: 'ORB-030', end: true },
  { to: ROUTES.today, labelKey: 'nav.today', ticket: 'ORB-032' },
  { to: ROUTES.projects, labelKey: 'nav.projects', ticket: 'ORB-019' },
  { to: ROUTES.tasks, labelKey: 'nav.tasks', ticket: 'ORB-020' },
  { to: ROUTES.calendar, labelKey: 'nav.calendar', ticket: 'ORB-027' },
  { to: ROUTES.reports, labelKey: 'nav.reports', ticket: 'ORB-043' },
  { to: ROUTES.admin, labelKey: 'nav.admin', ticket: 'ORB-045' },
];
