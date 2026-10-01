/**
 * Фильтры раздела. Чистая функция: порядок строк не меняет — его задал сервер (сначала то,
 * что требует внимания), фильтр только убирает лишнее.
 */

import type { ProjectCard } from './model';

export interface ProjectFilter {
  search: string;
  type: string;
  responsible: string;
  /** «Что держит Центр» — проекты, где у Центра есть роль (ТЗ 5). */
  center: boolean;
  /** Только проекты на ступени лестницы внимания. */
  attention: boolean;
}

export const NO_FILTER: ProjectFilter = {
  search: '',
  type: '',
  responsible: '',
  center: false,
  attention: false,
};

export function isFiltered(filter: ProjectFilter): boolean {
  return (
    filter.search.trim() !== '' ||
    filter.type !== '' ||
    filter.responsible !== '' ||
    filter.center ||
    filter.attention
  );
}

export function filterProjects(items: ProjectCard[], filter: ProjectFilter): ProjectCard[] {
  const needle = filter.search.trim().toLocaleLowerCase('ru');
  return items.filter(
    (card) =>
      (!needle ||
        card.title.toLocaleLowerCase('ru').includes(needle) ||
        card.code.toLocaleLowerCase('ru').includes(needle)) &&
      (!filter.type || card.type.code === filter.type) &&
      (!filter.responsible || card.responsible?.id === filter.responsible) &&
      (!filter.center || card.center_role !== null) &&
      (!filter.attention || card.step !== null),
  );
}
