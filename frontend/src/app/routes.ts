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
  /**
   * Вложенные адреса портфеля. `new` стоит раньше `:id` не по порядку в объекте, а по
   * правилу маршрутизатора: статический отрезок адреса точнее динамического и выигрывает
   * у него независимо от порядка объявления. Порядок здесь — для чтения.
   */
  projectNew: '/projects/new',
  projectCard: '/projects/:id',
  projectEdit: '/projects/:id/edit',
  tasks: '/tasks',
  calendar: '/calendar',
  reports: '/reports',
  admin: '/admin',
  login: '/login',
  forbidden: '/403',
} as const;

/**
 * Адрес карточки проекта по идентификатору.
 *
 * Функция, а не сборка строки по месту: `projectCard` содержит `:id`, и подставлять его
 * руками в четырёх местах — значит однажды подставить не туда и получить переход на
 * страницу «не найдено» вместо проекта.
 */
export function projectPath(id: string): string {
  return `${ROUTES.projects}/${id}`;
}

/** Адрес формы правки того же проекта. */
export function projectEditPath(id: string): string {
  return `${projectPath(id)}/edit`;
}

export interface NavItem {
  to: string;
  labelKey: string;
  /** Тикет, в котором появится содержимое экрана. */
  ticket: string;
  /** Точное совпадение адреса — нужно для корневого пункта. */
  end?: boolean;
  /** Экран готов: вместо заглушки подставляется настоящий компонент. */
  ready?: boolean;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { to: ROUTES.dashboard, labelKey: 'nav.dashboard', ticket: 'ORB-030', end: true },
  { to: ROUTES.today, labelKey: 'nav.today', ticket: 'ORB-032' },
  { to: ROUTES.projects, labelKey: 'nav.projects', ticket: 'ORB-019', ready: true },
  { to: ROUTES.tasks, labelKey: 'nav.tasks', ticket: 'ORB-020' },
  { to: ROUTES.calendar, labelKey: 'nav.calendar', ticket: 'ORB-027' },
  { to: ROUTES.reports, labelKey: 'nav.reports', ticket: 'ORB-043' },
  { to: ROUTES.admin, labelKey: 'nav.admin', ticket: 'ORB-045' },
];
