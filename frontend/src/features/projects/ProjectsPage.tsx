/**
 * Портфель проектов (ORB-019).
 *
 * **Фильтры живут в адресе, а не в состоянии компонента.** Это требование критерия
 * приёмки, и оно не про удобство разработчика: отфильтрованный список — то, что
 * помощник показывает руководителю и присылает ссылкой. Состояние, которое нельзя
 * передать ссылкой, приходится описывать словами.
 *
 * Цвет светофора приходит с сервера, а не вычисляется здесь: одно правило и одно место
 * (ADR-0005). Вторая реализация на клиенте разошлась бы с первой, и два экрана начали бы
 * показывать разное.
 */

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';

import { projectPath, ROUTES } from '../../app/routes';
import { HttpError } from '../../shared/api/client';
import { useSession } from '../../shared/auth/useSession';
import { formatDate } from '../../shared/time';
import { EmptyState } from '../../shared/ui/EmptyState';
import { ErrorState } from '../../shared/ui/ErrorState';
import { Skeleton } from '../../shared/ui/Skeleton';
import { AttachmentsButton, AttachmentsDrawer } from '../documents/AttachmentsDrawer';
import styles from './projects.module.css';
import type { Dictionaries, Project } from './api';
import { fetchDictionaries, fetchProjects } from './api';
import { ProjectBoard } from './ProjectBoard';
import { useMoveProject } from './useMoveProject';

/** Имена параметров адреса. Строками по месту не пишутся: опечатка тихо ломает фильтр. */
const PARAM = {
  status: 'status_code',
  direction: 'direction_id',
  priority: 'priority_code',
  curator: 'curator_person_id',
  health: 'health',
  search: 'search',
} as const;

/**
 * Вид экрана — тоже в адресе, но отдельно от фильтров: фильтры уходят в запрос к серверу,
 * а вид серверу не нужен. Список — вид по умолчанию и параметра не оставляет.
 */
const VIEW_PARAM = 'view';
const BOARD = 'board';

export function ProjectsPage() {
  const { t, i18n } = useTranslation();
  const [params, setParams] = useSearchParams();

  // Вложения живут в ящике поверх списка, пока нет карточки проекта (ORB-018).
  // Состояние здесь, а не в строке таблицы: ящик один на экран, и два открытых
  // одновременно — это два предпросмотра, борющихся за место.
  const [filesOf, setFilesOf] = useState<Project | null>(null);

  const { profile } = useSession();
  const mayEdit = profile?.role === 'assistant';
  const view = params.get(VIEW_PARAM) === BOARD ? BOARD : 'list';
  const [moveError, setMoveError] = useState<string | null>(null);

  // Явная запись, а не сборка из массива: тип должен знать, что значение есть у
  // каждого ключа, иначе каждое обращение к фильтру приходится проверять на пустоту.
  const filters: Record<string, string> = {
    [PARAM.status]: params.get(PARAM.status) ?? '',
    [PARAM.direction]: params.get(PARAM.direction) ?? '',
    [PARAM.priority]: params.get(PARAM.priority) ?? '',
    [PARAM.curator]: params.get(PARAM.curator) ?? '',
    [PARAM.health]: params.get(PARAM.health) ?? '',
    [PARAM.search]: params.get(PARAM.search) ?? '',
  };

  const filterOf = (name: string): string => filters[name] ?? '';

  const dictionaries = useQuery({
    queryKey: ['dictionaries', { includeInactive: false }],
    queryFn: () => fetchDictionaries(),
    staleTime: 10 * 60_000,
  });

  const projects = useQuery({
    queryKey: ['projects', filters],
    queryFn: () => fetchProjects(filters),
  });

  const moveProject = useMoveProject(['projects', filters]);

  const onMove = (project: Project, status: string, reason?: string) => {
    setMoveError(null);
    moveProject.mutate(
      { project, status, ...(reason === undefined ? {} : { reason }) },
      {
        onError: (error) => {
          // Слова сервера, а не свои: там сказано, почему именно перенос не принят.
          setMoveError(
            t('projects.board.moveFailed', {
              title: project.title,
              reason: error instanceof HttpError ? error.message : t('state.errorHint'),
            }),
          );
        },
      },
    );
  };

  function apply(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value === '') next.delete(name);
    else next.set(name, value);
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
        <h1 className={styles.title}>{t('nav.projects')}</h1>
        {projects.data !== undefined && (
          <span className={styles.count}>
            {t('projects.count', { count: projects.data.length })}
          </span>
        )}
        <div className={styles.views} role="group" aria-label={t('projects.viewLabel')}>
          <button
            type="button"
            className={styles.viewButton}
            aria-pressed={view !== BOARD}
            onClick={() => {
              apply(VIEW_PARAM, '');
            }}
          >
            {t('projects.viewList')}
          </button>
          <button
            type="button"
            className={styles.viewButton}
            aria-pressed={view === BOARD}
            onClick={() => {
              apply(VIEW_PARAM, BOARD);
            }}
          >
            {t('projects.viewBoard')}
          </button>
        </div>

        {/* Кнопка создания — в шапке списка и только у помощника. Руководителю она
            показывала бы действие, которое сервер ему всё равно не даст (ADR-0011). */}
        {mayEdit && (
          <Link className={styles.create} to={ROUTES.projectNew}>
            {t('projects.form.createTitle')}
          </Link>
        )}
      </header>

      <div className={styles.filters}>
        <input
          type="search"
          className={styles.search}
          placeholder={t('projects.searchPlaceholder')}
          aria-label={t('projects.searchPlaceholder')}
          value={filterOf(PARAM.search)}
          onChange={(event) => {
            apply(PARAM.search, event.target.value);
          }}
        />

        <Select
          label={t('projects.filterDirection')}
          value={filterOf(PARAM.direction)}
          onChange={(value) => {
            apply(PARAM.direction, value);
          }}
          options={(dictionaries.data?.directions ?? []).map((item) => ({
            value: item.id,
            label: localized(item),
          }))}
          anyLabel={t('projects.anyDirection')}
        />

        <Select
          label={t('projects.filterStatus')}
          value={filterOf(PARAM.status)}
          onChange={(value) => {
            apply(PARAM.status, value);
          }}
          options={(dictionaries.data?.project_statuses ?? []).map((item) => ({
            value: item.code,
            label: localized(item),
          }))}
          anyLabel={t('projects.anyStatus')}
        />

        <Select
          label={t('projects.filterPriority')}
          value={filterOf(PARAM.priority)}
          onChange={(value) => {
            apply(PARAM.priority, value);
          }}
          options={(dictionaries.data?.priorities ?? []).map((item) => ({
            value: item.code,
            label: localized(item),
          }))}
          anyLabel={t('projects.anyPriority')}
        />

        <Select
          label={t('projects.filterHealth')}
          value={filterOf(PARAM.health)}
          onChange={(value) => {
            apply(PARAM.health, value);
          }}
          options={(['red', 'yellow', 'green', 'grey'] as const).map((value) => ({
            value,
            label: t(`health.${value}`),
          }))}
          anyLabel={t('projects.anyHealth')}
        />
      </div>

      {projects.isPending && <Skeleton count={4} height={44} />}
      {projects.isError && (
        <ErrorState
          onRetry={() => {
            void projects.refetch();
          }}
        />
      )}
      {projects.data?.length === 0 && <EmptyState />}

      {moveError !== null && (
        <p className={styles.moveError} role="alert">
          {moveError}
        </p>
      )}

      {projects.data !== undefined && projects.data.length > 0 && view !== BOARD && (
        <ProjectTable
          projects={projects.data}
          dictionaries={dictionaries.data}
          onOpenFiles={setFilesOf}
        />
      )}

      {projects.data !== undefined &&
        projects.data.length > 0 &&
        view === BOARD &&
        dictionaries.data !== undefined && (
          <ProjectBoard
            projects={projects.data}
            dictionaries={dictionaries.data}
            mayEdit={mayEdit}
            onMove={onMove}
            onOpenFiles={setFilesOf}
          />
        )}

      {filesOf !== null && (
        <AttachmentsDrawer
          target="project"
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

function ProjectTable({
  projects,
  dictionaries,
  onOpenFiles,
}: {
  projects: Project[];
  dictionaries: Dictionaries | undefined;
  onOpenFiles: (project: Project) => void;
}) {
  const { t, i18n } = useTranslation();

  const statusName = (code: string) => {
    const entry = dictionaries?.project_statuses.find((item) => item.code === code);
    if (!entry) return code;
    return i18n.language === 'uz-Cyrl'
      ? entry.name.uz_cyrl
      : i18n.language === 'uz-Latn'
        ? entry.name.uz_latn
        : entry.name.ru;
  };

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">{t('projects.columnCode')}</th>
            <th scope="col">{t('projects.columnTitle')}</th>
            <th scope="col">{t('projects.columnStatus')}</th>
            <th scope="col">{t('projects.columnDue')}</th>
            <th scope="col">{t('projects.columnProgress')}</th>
            {/* Столбец действия, а не данных: заголовка у него нет, но он должен быть
                назван — иначе программа чтения с экрана объявляет пустую ячейку. */}
            <th scope="col">
              <span className={styles.srOnly}>{t('documents.title')}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {projects.map((project) => (
            <tr key={project.id}>
              <td className={styles.code}>{project.code}</td>
              <td>
                {/* Название — ссылка на карточку, а не текст: открыть проект иначе
                    нечем, и это первое, чего ждут от списка. */}
                <Link className={styles.projectLink} to={projectPath(project.id)}>
                  {project.title}
                </Link>
                {project.impediment !== null && (
                  <span
                    className={project.impediment_is_active ? styles.impediment : styles.stale}
                    title={project.impediment}
                  >
                    {project.impediment}
                  </span>
                )}
              </td>
              <td>
                <span className={`${styles.health} ${styles[project.health]}`}>
                  {statusName(project.status_code)}
                </span>
              </td>
              <td className={styles.due}>{formatDate(project.due_on)}</td>
              <td>
                <div
                  className={styles.progressTrack}
                  role="progressbar"
                  aria-valuenow={project.progress_pct}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={t('projects.columnProgress')}
                >
                  <div
                    className={styles.progressFill}
                    style={{ width: `${String(project.progress_pct)}%` }}
                  />
                </div>
              </td>
              <td className={styles.filesCell}>
                <AttachmentsButton
                  label={t('documents.open', { name: project.title })}
                  onOpen={() => {
                    onOpenFiles(project);
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
