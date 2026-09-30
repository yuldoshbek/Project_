/**
 * Фильтры раздела. Чистая функция: порядок не меняет — его задал сервер, фильтр только
 * убирает лишнее.
 */

import type { TaskCard } from './model';

export interface TaskFilter {
  search: string;
  assignee: string;
  type: string;
  /** Проект: `''` — все, `'none'` — без проекта, иначе идентификатор. */
  project: string;
  /** Только задачи на ступени лестницы внимания. */
  attention: boolean;
}

export const NO_FILTER: TaskFilter = {
  search: '',
  assignee: '',
  type: '',
  project: '',
  attention: false,
};

export function isFiltered(filter: TaskFilter): boolean {
  return (
    filter.search.trim() !== '' ||
    filter.assignee !== '' ||
    filter.type !== '' ||
    filter.project !== '' ||
    filter.attention
  );
}

export function filterTasks(items: TaskCard[], filter: TaskFilter): TaskCard[] {
  const needle = filter.search.trim().toLocaleLowerCase('ru');
  return items.filter(
    (task) =>
      (!needle ||
        task.title.toLocaleLowerCase('ru').includes(needle) ||
        task.code.toLocaleLowerCase('ru').includes(needle)) &&
      (!filter.assignee || task.assignee?.id === filter.assignee) &&
      (!filter.type || task.type?.code === filter.type) &&
      (!filter.project ||
        (filter.project === 'none'
          ? task.project === null
          : task.project?.id === filter.project)) &&
      (!filter.attention || task.step !== null),
  );
}
