/**
 * База задач (ORB-020).
 *
 * Экран, который заменяет Excel. Отсюда три вещи, которых в обычном списке не бывает:
 * сортировка по любой колонке, выбор видимых колонок и выгрузка ровно той выборки,
 * которая сейчас на экране.
 *
 * **Просрочка — выделение, а не колонка статуса.** Задача бывает «в работе» и
 * просроченной одновременно ([ADR-0004](../../../../docs/adr/ADR-0004-overdue-is-computed.md)),
 * и выносить её в отдельный статус значило бы потерять, чем она была до наступления
 * срока. Поэтому строка помечается цветом, а статус остаётся своим.
 *
 * Фильтры и выбор колонок живут в адресе: и то и другое — то, чем делятся ссылкой.
 */

import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import type { Dictionaries } from '../projects/api';
import { fetchDictionaries } from '../projects/api';
import { EmptyState } from '../../shared/ui/EmptyState';
import { ErrorState } from '../../shared/ui/ErrorState';
import { Skeleton } from '../../shared/ui/Skeleton';
import { AttachmentsButton, AttachmentsDrawer } from '../documents/AttachmentsDrawer';
import { formatDate } from '../../shared/time';
import type { Person, Task } from './api';
import { fetchPeople, fetchTasks, fetchTasksFile } from './api';
import styles from './tasks.module.css';

const PARAM = {
  status: 'status',
  priority: 'priority_code',
  assignee: 'assignee_person_id',
  curator: 'curator_person_id',
  direction: 'direction_id',
  overdue: 'overdue',
  control: 'is_control',
  search: 'search',
} as const;

/** Колонки таблицы. Скрытые перечисляются в адресе, чтобы вид переживал ссылку. */
const COLUMNS = ['code', 'title', 'status', 'priority', 'assignee', 'checklist', 'due'] as const;
type Column = (typeof COLUMNS)[number];

/**
 * Класс ячейки для колонки.
 *
 * Имена разведены намеренно. Пока класс брался по имени колонки, `title` попадал в
 * `.title` — класс заголовка страницы, — и в таблицу протекал его кегль: названия задач
 * набирались в полтора раза крупнее остальных ячеек, каждая строка переносилась на две,
 * и на экран помещалось вдвое меньше задач. Совпадение имён ничем себя не проявляет,
 * кроме вида.
 */
const CELL_CLASS: Record<Column, string> = {
  code: 'cellCode',
  title: 'cellTitle',
  status: 'cellStatus',
  priority: 'cellPriority',
  assignee: 'cellAssignee',
  checklist: 'cellChecklist',
  due: 'cellDue',
};

/**
 * Поле, по которому сортирует сервер.
 *
 * `null` — колонка не сортируется. Чек-лист именно такой: сортировать по нему значило бы
 * ставить рядом «1 из 2» и «50 из 100», между которыми нет порядка, полезного человеку.
 * Заголовок такой колонки не притворяется кнопкой — иначе щелчок по нему молча ничего не
 * делает, и это читается как поломка.
 */
const SORT_FIELD: Record<Column, string | null> = {
  code: 'code',
  title: 'title',
  status: 'status',
  priority: 'priority_code',
  assignee: 'assignee',
  checklist: null,
  due: 'due_at',
};

const HIDDEN_PARAM = 'hide';
const SORT_PARAM = 'sort_by';
const DESC_PARAM = 'descending';

export function TasksPage() {
  const { t, i18n } = useTranslation();
  const [params, setParams] = useSearchParams();

  // Вложения живут в ящике поверх списка, пока нет карточки задачи (ORB-022).
  const [filesOf, setFilesOf] = useState<Task | null>(null);

  const filters: Record<string, string> = {};
  for (const name of Object.values(PARAM)) filters[name] = params.get(name) ?? '';
  const filterOf = (name: string): string => filters[name] ?? '';

  const sortBy = params.get(SORT_PARAM) ?? 'due_at';
  const descending = params.get(DESC_PARAM) === 'true';
  const hidden = new Set((params.get(HIDDEN_PARAM) ?? '').split(',').filter(Boolean));

  const query = { ...filters, [SORT_PARAM]: sortBy, [DESC_PARAM]: String(descending) };

  const dictionaries = useQuery({
    queryKey: ['dictionaries'],
    queryFn: fetchDictionaries,
    staleTime: 10 * 60_000,
  });
  const people = useQuery({ queryKey: ['people'], queryFn: fetchPeople, staleTime: 10 * 60_000 });
  // Прошлый ответ остаётся на экране, пока идёт следующий запрос. Иначе таблица
  // пропадает при каждом изменении фильтра и сортировки: страница подпрыгивает, а
  // заголовок, по которому только что щёлкнули, исчезает из-под курсора.
  const tasks = useQuery({
    queryKey: ['tasks', query],
    queryFn: () => fetchTasks(query),
    placeholderData: keepPreviousData,
  });

  // Сохранение — действие, а не переход: файл приходит ответом на запрос с токеном,
  // и отдать его браузеру можно только так.
  const download = useMutation({
    mutationFn: () => fetchTasksFile(query),
    onSuccess: ({ blob, filename }) => {
      const href = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = href;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(href);
    },
  });

  function apply(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value === '') next.delete(name);
    else next.set(name, value);
    setParams(next, { replace: true });
  }

  function sortOn(column: Column) {
    const field = SORT_FIELD[column];
    if (field === null) return;
    const next = new URLSearchParams(params);
    next.set(SORT_PARAM, field);
    next.set(DESC_PARAM, String(sortBy === field && !descending));
    setParams(next, { replace: true });
  }

  function toggleColumn(column: Column) {
    const next = new URLSearchParams(params);
    const updated = new Set(hidden);
    if (updated.has(column)) updated.delete(column);
    else updated.add(column);

    if (updated.size === 0) next.delete(HIDDEN_PARAM);
    else next.set(HIDDEN_PARAM, [...updated].join(','));
    setParams(next, { replace: true });
  }

  const localized = (entry: { name: { ru: string; uz_cyrl: string; uz_latn: string } }) =>
    i18n.language === 'uz-Cyrl'
      ? entry.name.uz_cyrl
      : i18n.language === 'uz-Latn'
        ? entry.name.uz_latn
        : entry.name.ru;

  return (
    <section>
      <header className={styles.head}>
        <h1 className={styles.title}>{t('nav.tasks')}</h1>
        {tasks.data !== undefined && (
          <span className={styles.count}>{t('tasks.count', { count: tasks.data.length })}</span>
        )}
        <button
          type="button"
          className={styles.export}
          onClick={() => {
            download.mutate();
          }}
          disabled={download.isPending}
        >
          {download.isPending ? t('tasks.exporting') : t('tasks.export')}
        </button>
      </header>

      <div className={styles.filters}>
        <input
          type="search"
          className={styles.search}
          placeholder={t('tasks.searchPlaceholder')}
          aria-label={t('tasks.searchPlaceholder')}
          value={filterOf(PARAM.search)}
          onChange={(event) => {
            apply(PARAM.search, event.target.value);
          }}
        />

        <Select
          label={t('tasks.filterStatus')}
          value={filterOf(PARAM.status)}
          onChange={(value) => {
            apply(PARAM.status, value);
          }}
          options={(dictionaries.data?.task_statuses ?? []).map((item) => ({
            value: item.code,
            label: localized(item),
          }))}
          anyLabel={t('tasks.anyStatus')}
        />

        <Select
          label={t('tasks.filterPriority')}
          value={filterOf(PARAM.priority)}
          onChange={(value) => {
            apply(PARAM.priority, value);
          }}
          options={(dictionaries.data?.priorities ?? []).map((item) => ({
            value: item.code,
            label: localized(item),
          }))}
          anyLabel={t('tasks.anyPriority')}
        />

        <Select
          label={t('tasks.filterAssignee')}
          value={filterOf(PARAM.assignee)}
          onChange={(value) => {
            apply(PARAM.assignee, value);
          }}
          options={(people.data ?? []).map((person) => ({
            value: person.id,
            label: person.full_name,
          }))}
          anyLabel={t('tasks.anyAssignee')}
        />

        <Select
          label={t('tasks.filterCurator')}
          value={filterOf(PARAM.curator)}
          onChange={(value) => {
            apply(PARAM.curator, value);
          }}
          options={(people.data ?? []).map((person) => ({
            value: person.id,
            label: person.full_name,
          }))}
          anyLabel={t('tasks.anyCurator')}
        />

        <Select
          label={t('tasks.filterDirection')}
          value={filterOf(PARAM.direction)}
          onChange={(value) => {
            apply(PARAM.direction, value);
          }}
          options={(dictionaries.data?.directions ?? []).map((item) => ({
            value: item.id,
            label: localized(item),
          }))}
          anyLabel={t('tasks.anyDirection')}
        />

        <label className={styles.toggle}>
          <input
            type="checkbox"
            checked={filterOf(PARAM.overdue) === 'true'}
            onChange={(event) => {
              apply(PARAM.overdue, event.target.checked ? 'true' : '');
            }}
          />
          {t('tasks.onlyOverdue')}
        </label>

        <label className={styles.toggle}>
          <input
            type="checkbox"
            checked={filterOf(PARAM.control) === 'true'}
            onChange={(event) => {
              apply(PARAM.control, event.target.checked ? 'true' : '');
            }}
          />
          {t('tasks.onlyControl')}
        </label>
      </div>

      <details className={styles.columns}>
        <summary className={styles.columnsSummary}>{t('tasks.columns')}</summary>
        {/* Название колонки звучит на экране трижды — фильтром, заголовком сортировки и
            этой галочкой. Группа с именем возвращает каждому из трёх свой смысл. */}
        <div className={styles.columnsList} role="group" aria-label={t('tasks.columns')}>
          {COLUMNS.map((column) => (
            <label key={column} className={styles.toggle}>
              <input
                type="checkbox"
                checked={!hidden.has(column)}
                onChange={() => {
                  toggleColumn(column);
                }}
              />
              {t(`tasks.column.${column}`)}
            </label>
          ))}
        </div>
      </details>

      {download.isError && <p className={styles.exportError}>{t('tasks.exportFailed')}</p>}

      {tasks.isPending && <Skeleton count={5} height={40} />}
      {tasks.isError && (
        <ErrorState
          onRetry={() => {
            void tasks.refetch();
          }}
        />
      )}
      {tasks.data?.length === 0 && <EmptyState />}

      {tasks.data !== undefined && tasks.data.length > 0 && (
        <TaskTable
          tasks={tasks.data}
          hidden={hidden}
          sortBy={sortBy}
          descending={descending}
          onSort={sortOn}
          dictionaries={dictionaries.data}
          people={people.data ?? []}
          onOpenFiles={setFilesOf}
        />
      )}

      {filesOf !== null && (
        <AttachmentsDrawer
          target="task"
          entityId={filesOf.id}
          title={filesOf.title}
          onClose={() => {
            setFilesOf(null);
          }}
        />
      )}
    </section>
  );
}

/**
 * Прогресс чек-листа в строке списка.
 *
 * У задачи без чек-листа ячейка пуста. Не «0 %» и не «0 из 0»: ноль означает «взялись и
 * не сделали» — на экране это тревожный знак, а отсутствие чек-листа не сообщает ни о
 * чём. Различие приходит с сервера полем `checklist_percent`, равным `null`.
 *
 * Число и полоса вместе, а не одна полоса: полоса показывает «много или мало» с одного
 * взгляда, а «7 из 9» отвечает на вопрос «сколько осталось», ради которого в чек-лист и
 * заглядывают.
 */
function Checklist({ task }: { task: Task }) {
  const { t } = useTranslation();

  if (task.checklist_percent === null) return null;

  return (
    <span
      className={styles.checklist}
      title={t('tasks.checklistOf', {
        done: task.checklist_done,
        total: task.checklist_total,
      })}
    >
      <span
        className={styles.checklistBar}
        role="progressbar"
        aria-valuenow={task.checklist_percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={t('tasks.column.checklist')}
      >
        <span
          className={styles.checklistFill}
          style={{ width: `${String(task.checklist_percent)}%` }}
        />
      </span>
      <span className={styles.checklistCount}>
        {task.checklist_done}/{task.checklist_total}
      </span>
    </span>
  );
}

function Select({
  label,
  value,
  onChange,
  options,
  anyLabel,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  anyLabel: string;
}) {
  return (
    <label className={styles.filter}>
      <span className={styles.filterLabel}>{label}</span>
      <select
        className={styles.select}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      >
        <option value="">{anyLabel}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function TaskTable({
  tasks,
  hidden,
  sortBy,
  descending,
  onSort,
  dictionaries,
  people,
  onOpenFiles,
}: {
  tasks: Task[];
  hidden: Set<string>;
  sortBy: string;
  descending: boolean;
  onSort: (column: Column) => void;
  dictionaries: Dictionaries | undefined;
  people: Person[];
  onOpenFiles: (task: Task) => void;
}) {
  const { t, i18n } = useTranslation();

  const nameOf = (code: string, kind: 'task_statuses' | 'priorities') => {
    const entry = dictionaries?.[kind]?.find((item) => item.code === code);
    if (!entry) return code;
    return i18n.language === 'uz-Cyrl'
      ? entry.name.uz_cyrl
      : i18n.language === 'uz-Latn'
        ? entry.name.uz_latn
        : entry.name.ru;
  };

  const personOf = (id: string | null) =>
    id === null ? '' : (people.find((person) => person.id === id)?.full_name ?? '');

  const fieldOf = (column: Column) => SORT_FIELD[column];

  const visible = COLUMNS.filter((column) => !hidden.has(column));

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            {visible.map((column) => (
              <th
                key={column}
                scope="col"
                aria-sort={
                  sortBy === fieldOf(column) ? (descending ? 'descending' : 'ascending') : 'none'
                }
              >
                {fieldOf(column) === null ? (
                  <span className={styles.plainHeader}>{t(`tasks.column.${column}`)}</span>
                ) : (
                  <button
                    type="button"
                    className={styles.sortButton}
                    onClick={() => {
                      onSort(column);
                    }}
                  >
                    {t(`tasks.column.${column}`)}
                  </button>
                )}
              </th>
            ))}
            {/* Столбец действия, а не данных: он не входит в выбор столбцов и не
                сортируется, но должен быть назван — иначе программа чтения с экрана
                объявляет пустую ячейку. */}
            <th scope="col">
              <span className={styles.srOnly}>{t('documents.title')}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((task) => (
            <tr key={task.id} className={task.is_overdue ? styles.overdue : undefined}>
              {visible.map((column) => (
                <td key={column} className={styles[CELL_CLASS[column]]}>
                  {column === 'code' && task.code}
                  {column === 'title' && (
                    <>
                      <span className={styles.taskTitle}>{task.title}</span>
                      {task.is_overdue && (
                        <span className={styles.overdueMark}>
                          {t('tasks.overdueBy', { count: task.days_overdue })}
                        </span>
                      )}
                    </>
                  )}
                  {column === 'status' && nameOf(task.status, 'task_statuses')}
                  {column === 'priority' && nameOf(task.priority_code, 'priorities')}
                  {column === 'assignee' && personOf(task.assignee_person_id)}
                  {column === 'checklist' && <Checklist task={task} />}
                  {column === 'due' && formatDate(task.due_at)}
                </td>
              ))}
              <td className={styles.filesCell}>
                <AttachmentsButton
                  label={t('documents.open', { name: task.title })}
                  onOpen={() => {
                    onOpenFiles(task);
                  }}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
