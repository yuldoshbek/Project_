/**
 * Быстрый ввод задачи строкой (ORB-087).
 *
 * **Почему это отдельный способ, а не «форма, только короче».** Задач вносят десятки в
 * неделю, проектов — единицы. Форма, которая стоит минуту, убивает учёт задач быстрее,
 * чем отсутствие формы: её начинают обходить, и через месяц в системе лежит четверть
 * работы. Норматив карточки — медиана не больше 30 секунд на задачу при десяти подряд.
 *
 * Отсюда три решения, каждое из которых съедает секунды:
 *
 * 1. **Два поля, а не десять.** Название и срок. Остальное берётся из контекста списка:
 *    проект, направление и исполнитель — из текущих фильтров. Человек, вносящий десять
 *    задач по одному проекту, уже отфильтровал список по нему — спрашивать снова значит
 *    спрашивать то, что известно.
 * 2. **Строка не уходит со страницы и не открывает ничего.** Список обновляется на
 *    месте; ни перехода, ни возврата, ни потери прокрутки и фильтров.
 * 3. **Курсор возвращается в название, и оно очищается.** Это и есть разница между
 *    тридцатью секундами и полутора минутами: следующую задачу начинают печатать сразу,
 *    не ища поле мышью. Срок при этом **остаётся** — десять задач подряд почти всегда
 *    имеют один срок, и перенабирать дату каждый раз пришлось бы десять раз.
 *
 * Приоритет здесь не спрашивается вовсе: он берётся обычным. Поле приоритета в быстром
 * вводе означало бы выбор на каждой задаче, а выбор, который делают десять раз подряд,
 * делают не думая — и портфель получает приоритеты, ничего не значащие.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { FormEvent } from 'react';
import { useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { HttpError } from '../../shared/api/client';
import type { TaskDraft } from './api';
import { createTask } from './api';
import styles from './tasks.module.css';

export interface QuickAddProps {
  /**
   * Фильтры списка. Из них берётся контекст: проект и исполнитель.
   *
   * Передаются целиком, а не разобранными по полям: набор фильтров экрана растёт, и
   * второй список их имён здесь разошёлся бы с первым.
   */
  filters: Record<string, string>;
  /** Ключ запроса списка — его и обновляем после записи. */
  queryKey: readonly unknown[];
  /** Приоритет по умолчанию: код «обычного» из справочника. */
  defaultPriority: string;
}

/** Срок вводится датой, а сервер ждёт момент. Конец рабочего дня — 18:00 в Ташкенте. */
const END_OF_DAY = 'T18:00:00+05:00';

export function QuickAdd({ filters, queryKey, defaultPriority }: QuickAddProps) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const ids = useId();

  const [title, setTitle] = useState('');
  const [due, setDue] = useState('');
  const titleField = useRef<HTMLInputElement>(null);
  const [added, setAdded] = useState<string | null>(null);

  const add = useMutation({
    mutationFn: (draft: TaskDraft) => createTask(draft),
    onSuccess: async (task) => {
      await client.invalidateQueries({ queryKey });
      setTitle('');
      // Срок не сбрасывается: десять задач подряд почти всегда имеют один срок.
      setAdded(task.code);
      titleField.current?.focus();
    },
  });

  const cleaned = title.trim();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (cleaned === '') return;

    add.mutate({
      title: cleaned,
      description: null,
      // Проект и исполнитель — из фильтров списка. Пустой фильтр даёт задачу вне
      // проекта, и это законное состояние: половина работы аппарата — поручения,
      // у которых проекта нет и не будет.
      project_id: filters.project_id === '' ? null : (filters.project_id ?? null),
      assignee_person_id:
        filters.assignee_person_id === '' ? null : (filters.assignee_person_id ?? null),
      status: 'new',
      priority_code: defaultPriority,
      due_at: due === '' ? null : `${due}${END_OF_DAY}`,
      // Плановый срок равен введённому: при быстром вводе план и факт совпадают, и
      // разводит их потом продление, а не ввод.
      planned_due_at: due === '' ? null : `${due}${END_OF_DAY}`,
      is_control: false,
    });
  };

  const message = add.error instanceof HttpError ? add.error.message : null;

  return (
    <form className={styles.quickAdd} onSubmit={submit}>
      <label className={styles.srOnly} htmlFor={`${ids}-title`}>
        {t('tasks.quick.title')}
      </label>
      <input
        id={`${ids}-title`}
        ref={titleField}
        className={styles.quickTitle}
        type="text"
        maxLength={300}
        autoComplete="off"
        placeholder={t('tasks.quick.placeholder')}
        value={title}
        onChange={(event) => {
          setTitle(event.target.value);
          setAdded(null);
        }}
      />

      <label className={styles.srOnly} htmlFor={`${ids}-due`}>
        {t('tasks.quick.due')}
      </label>
      <input
        id={`${ids}-due`}
        className={styles.quickDue}
        type="date"
        aria-label={t('tasks.quick.due')}
        value={due}
        onChange={(event) => {
          setDue(event.target.value);
        }}
      />

      <button type="submit" className={styles.quickSubmit} disabled={cleaned === ''}>
        {add.isPending ? t('tasks.quick.adding') : t('tasks.quick.add')}
      </button>

      {/* Что именно попало в список — номером. Полоса «сохранено» без номера не
          отличает удачу от того, что строку проглотили: список отсортирован и новая
          задача может оказаться не на виду.

          `role="status"`, а не `alert`: сообщение об успехе не должно перебивать
          набор следующей задачи, а именно набор здесь и идёт десять раз подряд. */}
      <p className={styles.quickHint} role="status">
        {added === null ? contextHint(filters, t) : t('tasks.quick.added', { code: added })}
      </p>

      {message !== null && (
        <p className={styles.quickError} role="alert">
          {message}
        </p>
      )}
    </form>
  );
}

/**
 * Что будет подставлено из фильтров — сказано до нажатия, а не после.
 *
 * Без этой строки быстрый ввод — это ввод втёмную: задача уезжает в проект, который
 * человек отфильтровал десять минут назад и уже забыл. Ошибку такого рода замечают на
 * пятой задаче, а исправлять приходится все пять.
 */
function contextHint(
  filters: Record<string, string>,
  t: (key: string) => string,
): string {
  const inProject = (filters.project_id ?? '') !== '';
  const assigned = (filters.assignee_person_id ?? '') !== '';

  if (inProject && assigned) return t('tasks.quick.contextBoth');
  if (inProject) return t('tasks.quick.contextProject');
  if (assigned) return t('tasks.quick.contextAssignee');
  return t('tasks.quick.contextNone');
}
