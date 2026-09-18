/**
 * Карточка проекта — короткая (ORB-086, заготовка под ORB-018).
 *
 * **Почему она здесь, а не в ORB-018.** Критерий приёмки ORB-086 требует, чтобы после
 * сохранения открывалась карточка, а не список, — а ORB-086 объявлен блокирующим
 * ORB-018, который эту карточку и делает. Круг замкнутый, и разорвать его можно двумя
 * способами: нарушить свой же критерий или сделать карточку в объёме, достаточном для
 * ответа на вопрос «сохранилось ли то, что я вводил». Выбрано второе.
 *
 * Поэтому здесь ровно те поля, которые есть в форме, и ни одного больше. Вехи, задачи,
 * файлы, партнёры, лента событий и правка полей на месте — это ORB-018, и внизу об этом
 * сказано вслух, чтобы пустое место не читалось как недоделка без причины.
 */

import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router-dom';

import { projectEditPath } from '../../app/routes';
import { useMayEdit } from '../../shared/mode/useMode';
import { formatDate } from '../../shared/time';
import { ErrorState } from '../../shared/ui/ErrorState';
import { Skeleton } from '../../shared/ui/Skeleton';
import type { Person, Project } from './api';
import { fetchDictionaries, fetchPeople, fetchProject, localizedName } from './api';
import styles from './form.module.css';
import listStyles from './projects.module.css';

export function ProjectCardPage() {
  const { id = '' } = useParams<'id'>();
  const { t, i18n } = useTranslation();
  const mayEdit = useMayEdit();

  const project = useQuery({ queryKey: ['project', id], queryFn: () => fetchProject(id) });
  const dictionaries = useQuery({
    queryKey: ['dictionaries', { includeInactive: true }],
    queryFn: () => fetchDictionaries(true),
    staleTime: 10 * 60_000,
  });
  const people = useQuery({
    queryKey: ['people', { includeInactive: true }],
    queryFn: () => fetchPeople(true),
    staleTime: 10 * 60_000,
  });

  if (project.isPending) return <Skeleton count={4} height={56} />;
  if (project.isError || project.data === undefined) {
    return (
      <ErrorState
        onRetry={() => {
          void project.refetch();
        }}
      />
    );
  }

  const data = project.data;
  const named = (entry: { name: { ru: string; uz_cyrl: string; uz_latn: string } } | undefined) =>
    entry === undefined ? null : localizedName(entry.name, i18n.language);

  return (
    <section className={styles.card}>
      <div className={styles.cardHead}>
        <span className={styles.cardCode}>{data.code}</span>
        <h1 className={styles.cardTitle}>{data.title}</h1>
        <span className={`${listStyles.health} ${listStyles[data.health]}`}>
          {t(`health.${data.health}`)}
        </span>
        {mayEdit && (
          <Link className={styles.secondary} to={projectEditPath(id)}>
            {t('projects.form.edit')}
          </Link>
        )}
      </div>

      <dl className={styles.facts}>
        <Fact name={t('projects.columnStatus')}>
          {named(dictionaries.data?.project_statuses.find((s) => s.code === data.status_code)) ??
            data.status_code}
        </Fact>
        <Fact name={t('projects.filterDirection')}>
          {named(dictionaries.data?.directions.find((d) => d.id === data.direction_id)) ??
            data.direction_id}
        </Fact>
        <Fact name={t('projects.filterPriority')}>
          {named(dictionaries.data?.priorities.find((p) => p.code === data.priority_code)) ??
            data.priority_code}
        </Fact>
        <Fact name={t('projects.form.curator')}>
          {curatorName(people.data, data) ?? t('projects.form.noCurator')}
        </Fact>
        <Fact name={t('projects.form.started')}>{formatDate(data.started_on)}</Fact>
        <Fact name={t('projects.columnDue')}>{formatDate(data.due_on)}</Fact>
        <Fact name={t('projects.columnProgress')}>
          {t('projects.board.percent', { value: data.progress_pct })}
          {data.progress_mode === 'auto' ? ` — ${t('projects.form.progressAuto')}` : ''}
        </Fact>
        <Fact name={t('projects.form.kind')}>
          {data.kind === 'mini' ? t('projects.form.kindMini') : t('projects.form.kindProject')}
        </Fact>
        {/* Выдача наружу показывается всегда, а не только когда она включена: поле,
            которое видно лишь в одном из двух состояний, читается как отсутствующее. */}
        <Fact name={t('projects.form.shareExternally')}>
          {data.share_externally ? t('projects.form.shareYes') : t('projects.form.shareNo')}
        </Fact>
        {data.status_reason !== null && (
          <Fact name={t('projects.board.reasonLabel')}>{data.status_reason}</Fact>
        )}
        {data.finished_on !== null && (
          <Fact name={t('projects.form.finished')}>{formatDate(data.finished_on)}</Fact>
        )}
        {data.impediment !== null && (
          <Fact name={t('projects.form.impediment')}>{data.impediment}</Fact>
        )}
        {data.description !== null && (
          <Fact name={t('projects.form.description')}>{data.description}</Fact>
        )}
        {data.budget_note !== null && (
          <Fact name={t('projects.form.budgetNote')}>{data.budget_note}</Fact>
        )}
      </dl>

      <p className={styles.pending}>{t('projects.form.cardPending')}</p>
    </section>
  );
}

function curatorName(people: Person[] | undefined, project: Project): string | null {
  if (project.curator_person_id === null) return null;
  return people?.find((person) => person.id === project.curator_person_id)?.full_name ?? null;
}

function Fact({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div>
      <dt className={styles.factName}>{name}</dt>
      <dd className={styles.factValue}>{children}</dd>
    </div>
  );
}
