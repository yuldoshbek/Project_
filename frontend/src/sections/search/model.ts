/**
 * Поиск по всем разделам — договор данных панели (ТЗ 6, допущение V19).
 *
 * Отвечает `GET /api/v1/search?q=` (`backend/app/api/routes/search.py`). Сервер ищет запрос
 * в двух написаниях — как набран и другой письменностью: «kosmik» находит поручение
 * «Космик…» (`backend/app/domain/search.py`). Экран только показывает находки и открывает
 * карточку их раздела.
 */

/** Короче двух знаков сервер не ищет: одна буква совпадает с половиной базы. */
export const MIN_LENGTH = 2;

export type HitKind =
  | 'program'
  | 'project'
  | 'task'
  | 'ijro'
  | 'letter'
  | 'organization'
  | 'agreement'
  | 'idea'
  | 'preparation';

export interface SearchHit {
  id: string;
  /** Название, тема письма, текст поручения или идеи — как в данных, без перевода. */
  title: string;
  /** Номер: код проекта и задачи, номер письма, краткое имя организации. */
  code: string | null;
  /** Чему принадлежит: проект задачи, документ поручения, организация письма. */
  context: string | null;
}

export interface SearchGroup {
  kind: HitKind;
  hits: SearchHit[];
  /** Нашлось больше, чем в группе: остальное — в разделе. */
  more: boolean;
}

export interface SearchView {
  query: string;
  groups: SearchGroup[];
}

export interface HitTarget {
  to: string;
  search: Record<string, string>;
}

/**
 * Куда ведёт находка: раздел и открытая карточка (`?open=`). У соглашения своей карточки
 * нет — оно живёт строкой вкладки «Соглашения», туда и ведёт находка.
 */
export function targetOf(kind: HitKind, id: string): HitTarget {
  switch (kind) {
    case 'program':
      return { to: '/programs', search: { open: id } };
    case 'project':
      return { to: '/projects', search: { open: id } };
    case 'task':
      return { to: '/tasks', search: { open: id } };
    case 'ijro':
      return { to: '/ijro', search: { view: 'assignments', open: id } };
    case 'letter':
      return { to: '/interaction', search: { view: 'letters', open: id } };
    case 'organization':
      return { to: '/interaction', search: { view: 'organizations', open: id } };
    case 'agreement':
      return { to: '/interaction', search: { view: 'agreements' } };
    case 'idea':
      return { to: '/ideas', search: { open: id } };
    case 'preparation':
      return { to: '/reports', search: { open: id } };
  }
}
