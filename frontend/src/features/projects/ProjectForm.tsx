/**
 * Форма создания и правки проекта (ORB-086).
 *
 * **Одна форма на два действия, а не две похожие.** Поля у создания и правки те же —
 * это поля `POST` и `PATCH /projects`; различаются только заголовок, надпись на кнопке
 * и то, откуда взяты начальные значения. Две формы разошлись бы на первом новом поле, и
 * разошлись бы молча: добавленное в одну в другой просто не появилось бы.
 *
 * **Стоимость ввода здесь — это и есть требование.** Данные вносит один человек вручную,
 * между делом (CLAUDE.md). Поэтому обязательных полей ровно столько, сколько требует
 * сервер, остальное убрано под «Подробности»: форма из четырнадцати полей, открытая
 * целиком, читается как анкета, а анкету заполняют один раз и больше не открывают.
 *
 * **Правила не дублируются.** Какой статус требует причину — говорит сервер полем
 * `requires_reason` в справочнике (`api.ts`), а не список «пауза и отмена» здесь. Что
 * срок не раньше начала — держит `CHECK` в базе, и здесь это выражено родным
 * ограничением поля `min`, а не вторым сравнением в коде: браузер подскажет до отправки,
 * а судит по-прежнему сервер. Проценты в режиме `auto` не отправляются вовсе.
 */

import type { FormEvent, ReactNode } from 'react';
import { cloneElement, isValidElement, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { HttpError } from '../../shared/api/client';
import type {
  Dictionaries,
  DictionaryItem,
  Person,
  Project,
  ProjectDraft,
  ProjectKind,
  ProgressMode,
} from './api';
import { localizedName } from './api';
import styles from './form.module.css';

export interface ProjectFormProps {
  /** Правится существующий проект; при создании поля пусты. */
  project?: Project;
  dictionaries: Dictionaries;
  people: Person[];
  /** Ошибка предыдущей попытки сохранить. Приходит снаружи: запрос делает страница. */
  error: HttpError | Error | null;
  saving: boolean;
  onSubmit: (draft: ProjectDraft) => void;
  onCancel: () => void;
}

/**
 * Начальные значения новой формы.
 *
 * Срок не подставляется: подставленный срок сохранят не читая, и через месяц у половины
 * проектов будет одна и та же дата, взявшаяся неизвестно откуда. Дата начала — сегодня,
 * потому что это единственное значение, которое почти всегда верно.
 *
 * `share_externally` — `true`, как умолчание в базе. Форма это умолчание **показывает**:
 * ровно в этом и был смысл поставить переключатель в ту же волну, что и форму
 * (ADR-0024, раздел «Плохо и существенно»).
 */
function blankDraft(dictionaries: Dictionaries, today: string): ProjectDraft {
  return {
    title: '',
    description: null,
    kind: 'project',
    share_externally: true,
    direction_id: dictionaries.directions[0]?.id ?? '',
    curator_person_id: null,
    status_code: dictionaries.project_statuses[0]?.code ?? '',
    status_reason: null,
    priority_code: normalPriority(dictionaries.priorities),
    started_on: today,
    due_on: '',
    finished_on: null,
    progress_pct: 0,
    progress_mode: 'auto',
    budget_note: null,
  };
}

/**
 * Приоритет по умолчанию — «обычный», а не первый в справочнике.
 *
 * Справочник отсортирован по важности, и первым стоит «срочно». Форма, открывающаяся на
 * «срочно», через месяц даёт портфель, где срочно всё, — то есть светофор, который
 * ничего не значит. Если кода `normal` в справочнике нет, берётся первый: отказаться
 * открывать форму из-за отсутствующего кода хуже, чем открыть её с чужим значением.
 */
function normalPriority(priorities: DictionaryItem[]): string {
  return (priorities.find((item) => item.code === 'normal') ?? priorities[0])?.code ?? '';
}

function draftOf(project: Project): ProjectDraft {
  return {
    title: project.title,
    description: project.description,
    kind: project.kind,
    share_externally: project.share_externally,
    direction_id: project.direction_id,
    curator_person_id: project.curator_person_id,
    status_code: project.status_code,
    status_reason: project.status_reason,
    priority_code: project.priority_code,
    started_on: project.started_on,
    due_on: project.due_on,
    finished_on: project.finished_on,
    progress_pct: project.progress_pct,
    progress_mode: project.progress_mode,
    budget_note: project.budget_note,
  };
}

/** Пустая строка в необязательном поле — это `null`, а не `''`. */
function orNull(value: string): string | null {
  const cleaned = value.trim();
  return cleaned === '' ? null : cleaned;
}

export function ProjectForm({
  project,
  dictionaries,
  people,
  error,
  saving,
  onSubmit,
  onCancel,
}: ProjectFormProps) {
  const { t, i18n } = useTranslation();
  const ids = useId();

  const today = new Date().toISOString().slice(0, 10);
  const [draft, setDraft] = useState<ProjectDraft>(() =>
    project === undefined ? blankDraft(dictionaries, today) : draftOf(project),
  );
  const [showDetails, setShowDetails] = useState(false);

  /** Идентификаторы полей от одного корня: `useId` даёт уникальный на каждую форму. */
  const field = (key: string) => `${ids}-${key}`;
  const named = (entry: { name: { ru: string; uz_cyrl: string; uz_latn: string } }) =>
    localizedName(entry.name, i18n.language);

  function set<K extends keyof ProjectDraft>(key: K, value: ProjectDraft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  const status = dictionaries.project_statuses.find((item) => item.code === draft.status_code);
  const reasonRequired = status?.requires_reason === true;
  const reasonMissing = reasonRequired && orNull(draft.status_reason ?? '') === null;

  const httpError = error instanceof HttpError ? error : null;
  const fieldErrors = httpError?.fieldErrors ?? {};

  /**
   * Сообщение под полем: своё, если оно есть, иначе отказ сервера по этому полю.
   *
   * Своё проверяется только там, где сервер откажет наверняка, — иначе получаются два
   * набора правил, и первым расходится тот, что здесь.
   */
  const messageFor = (key: string, own?: string | false): string | null =>
    (own === false ? null : own) ?? fieldErrors[key] ?? null;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (reasonMissing) return;

    onSubmit({
      ...draft,
      title: draft.title.trim(),
      description: orNull(draft.description ?? ''),
      status_reason: orNull(draft.status_reason ?? ''),
      budget_note: orNull(draft.budget_note ?? ''),
      curator_person_id: draft.curator_person_id === '' ? null : draft.curator_person_id,
      finished_on: draft.finished_on === '' ? null : draft.finished_on,
    });
  };

  return (
    <form className={styles.form} onSubmit={submit} noValidate>
      <h1 className={styles.title}>
        {project === undefined
          ? t('projects.form.createTitle')
          : t('projects.form.editTitle', { code: project.code })}
      </h1>

      {error !== null && (
        <p className={styles.formError} role="alert">
          {error.message}
        </p>
      )}

      <Field
        id={field('title')}
        label={t('projects.form.name')}
        message={messageFor('title')}
        required
      >
        <input
          id={field('title')}
          className={styles.input}
          type="text"
          maxLength={300}
          required
          autoComplete="off"
          value={draft.title}
          onChange={(event) => {
            set('title', event.target.value);
          }}
        />
      </Field>

      <div className={styles.pair}>
        <Field
          id={field('direction')}
          label={t('projects.filterDirection')}
          message={messageFor('direction_id')}
          required
        >
          <select
            id={field('direction')}
            className={styles.select}
            required
            value={draft.direction_id}
            onChange={(event) => {
              set('direction_id', event.target.value);
            }}
          >
            {dictionaries.directions.map((item) => (
              <option key={item.id} value={item.id}>
                {named(item)}
              </option>
            ))}
          </select>
        </Field>

        <Field
          id={field('curator')}
          label={t('projects.form.curator')}
          message={messageFor('curator_person_id')}
          hint={t('projects.form.curatorHint')}
        >
          <select
            id={field('curator')}
            className={styles.select}
            value={draft.curator_person_id ?? ''}
            onChange={(event) => {
              set('curator_person_id', event.target.value === '' ? null : event.target.value);
            }}
          >
            <option value="">{t('projects.form.noCurator')}</option>
            {people.map((person) => (
              <option key={person.id} value={person.id}>
                {person.position === null
                  ? person.full_name
                  : `${person.full_name} — ${person.position}`}
              </option>
            ))}
          </select>
        </Field>
      </div>

      <div className={styles.pair}>
        <Field
          id={field('status')}
          label={t('projects.filterStatus')}
          message={messageFor('status_code')}
          required
        >
          <select
            id={field('status')}
            className={styles.select}
            required
            value={draft.status_code}
            onChange={(event) => {
              set('status_code', event.target.value);
            }}
          >
            {dictionaries.project_statuses.map((item) => (
              <option key={item.code} value={item.code}>
                {named(item)}
              </option>
            ))}
          </select>
        </Field>

        <Field
          id={field('priority')}
          label={t('projects.filterPriority')}
          message={messageFor('priority_code')}
          required
        >
          <select
            id={field('priority')}
            className={styles.select}
            required
            value={draft.priority_code}
            onChange={(event) => {
              set('priority_code', event.target.value);
            }}
          >
            {dictionaries.priorities.map((item) => (
              <option key={item.code} value={item.code}>
                {named(item)}
              </option>
            ))}
          </select>
        </Field>
      </div>

      {/* Причина показывается только когда справочник сказал, что она нужна: постоянное
          поле «причина статуса» на форме создания — это вопрос, на который в девяти
          случаях из десяти нечего ответить. */}
      {reasonRequired && (
        <Field
          id={field('reason')}
          label={t('projects.board.reasonLabel')}
          hint={t('projects.board.reasonHint')}
          message={messageFor('status_reason', reasonMissing && t('projects.form.reasonRequired'))}
          required
        >
          <textarea
            id={field('reason')}
            className={styles.textarea}
            rows={2}
            value={draft.status_reason ?? ''}
            onChange={(event) => {
              set('status_reason', event.target.value);
            }}
          />
        </Field>
      )}

      <div className={styles.pair}>
        <Field
          id={field('started')}
          label={t('projects.form.started')}
          message={messageFor('started_on')}
          required
        >
          <input
            id={field('started')}
            className={styles.input}
            type="date"
            required
            value={draft.started_on}
            onChange={(event) => {
              set('started_on', event.target.value);
            }}
          />
        </Field>

        <Field
          id={field('due')}
          label={t('projects.columnDue')}
          message={messageFor('due_on')}
          required
        >
          {/* `min` — родное ограничение поля, а не второе сравнение в коде: судит
              по-прежнему `CHECK due_on >= started_on` в базе. */}
          <input
            id={field('due')}
            className={styles.input}
            type="date"
            required
            min={draft.started_on}
            value={draft.due_on}
            onChange={(event) => {
              set('due_on', event.target.value);
            }}
          />
        </Field>
      </div>

      <Field
        id={field('share')}
        label={t('projects.form.shareExternally')}
        hint={t('projects.form.shareExternallyHint')}
        inline
      >
        <input
          id={field('share')}
          className={styles.checkbox}
          type="checkbox"
          checked={draft.share_externally}
          onChange={(event) => {
            set('share_externally', event.target.checked);
          }}
        />
      </Field>

      <button
        type="button"
        className={styles.disclosure}
        aria-expanded={showDetails}
        onClick={() => {
          setShowDetails((open) => !open);
        }}
      >
        {showDetails ? t('projects.form.hideDetails') : t('projects.form.showDetails')}
      </button>

      {showDetails && (
        <div className={styles.details}>
          <Field
            id={field('description')}
            label={t('projects.form.description')}
            message={messageFor('description')}
          >
            <textarea
              id={field('description')}
              className={styles.textarea}
              rows={3}
              value={draft.description ?? ''}
              onChange={(event) => {
                set('description', event.target.value);
              }}
            />
          </Field>

          <div className={styles.pair}>
            <Field
              id={field('kind')}
              label={t('projects.form.kind')}
              hint={t('projects.form.kindHint')}
            >
              <select
                id={field('kind')}
                className={styles.select}
                value={draft.kind}
                onChange={(event) => {
                  set('kind', event.target.value as ProjectKind);
                }}
              >
                <option value="project">{t('projects.form.kindProject')}</option>
                <option value="mini">{t('projects.form.kindMini')}</option>
              </select>
            </Field>

            <Field
              id={field('finished')}
              label={t('projects.form.finished')}
              message={messageFor('finished_on')}
            >
              <input
                id={field('finished')}
                className={styles.input}
                type="date"
                min={draft.started_on}
                value={draft.finished_on ?? ''}
                onChange={(event) => {
                  set('finished_on', event.target.value === '' ? null : event.target.value);
                }}
              />
            </Field>
          </div>

          <div className={styles.pair}>
            <Field
              id={field('progressMode')}
              label={t('projects.form.progressMode')}
              hint={
                draft.progress_mode === 'auto'
                  ? t('projects.form.progressAutoHint')
                  : t('projects.form.progressManualHint')
              }
            >
              <select
                id={field('progressMode')}
                className={styles.select}
                value={draft.progress_mode}
                onChange={(event) => {
                  set('progress_mode', event.target.value as ProgressMode);
                }}
              >
                <option value="auto">{t('projects.form.progressAuto')}</option>
                <option value="manual">{t('projects.form.progressManual')}</option>
              </select>
            </Field>

            {/* Поля процента в режиме `auto` нет вовсе, а не «есть и не работает».
                Заблокированное поле рядом с числом, которое считает сервер, выглядит
                сломанным — и первое, что делают, это пробуют его починить. */}
            {draft.progress_mode === 'manual' && (
              <Field
                id={field('progress')}
                label={t('projects.columnProgress')}
                message={messageFor('progress_pct')}
              >
                <input
                  id={field('progress')}
                  className={styles.input}
                  type="number"
                  min={0}
                  max={100}
                  step={1}
                  value={draft.progress_pct}
                  onChange={(event) => {
                    set('progress_pct', Number(event.target.value));
                  }}
                />
              </Field>
            )}
          </div>

          <Field
            id={field('budget')}
            label={t('projects.form.budgetNote')}
            hint={t('projects.form.budgetNoteHint')}
            message={messageFor('budget_note')}
          >
            <textarea
              id={field('budget')}
              className={styles.textarea}
              rows={2}
              value={draft.budget_note ?? ''}
              onChange={(event) => {
                set('budget_note', event.target.value);
              }}
            />
          </Field>
        </div>
      )}

      <div className={styles.actions}>
        <button type="button" className={styles.secondary} onClick={onCancel} disabled={saving}>
          {t('projects.form.cancel')}
        </button>
        <button type="submit" className={styles.primary} disabled={saving}>
          {saving ? t('projects.form.saving') : t('projects.form.save')}
        </button>
      </div>
    </form>
  );
}

/**
 * Обвязка поля: подпись, подсказка, сообщение об отказе.
 *
 * Подпись связана с полем через `htmlFor`, подсказка и ошибка — через
 * `aria-describedby`, и всё это в одном месте: повторённое у четырнадцати полей,
 * у пятнадцатого оно будет забыто. Ошибка стоит **у поля**, а не только сверху формы:
 * общая строка заставляет искать поле глазами.
 */
function Field({
  id,
  label,
  hint,
  message,
  required = false,
  inline = false,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  message?: string | null;
  required?: boolean;
  inline?: boolean;
  children: ReactNode;
}) {
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;

  const hasMessage = message !== null && message !== undefined && message !== '';
  const described = [hint === undefined ? null : hintId, hasMessage ? errorId : null]
    .filter((value) => value !== null)
    .join(' ');

  return (
    <div className={inline ? styles.fieldInline : styles.field}>
      {/* Звёздочка рисуется в CSS, а не текстом в разметке: обязательность полю уже
          объявлена атрибутом `required`, и программа чтения с экрана называет её сама.
          Звёздочка в разметке была бы второй, произносимой копией того же смысла. */}
      <label
        className={required ? `${styles.label} ${styles.isRequired}` : styles.label}
        htmlFor={id}
      >
        {label}
      </label>

      {/* Описание подставляется полю, а не обёртке: связь нужна самому элементу ввода. */}
      <div className={styles.control}>{describe(children, described, hasMessage)}</div>

      {hint !== undefined && (
        <p id={hintId} className={styles.hint}>
          {hint}
        </p>
      )}
      {hasMessage && (
        <p id={errorId} className={styles.fieldError} role="alert">
          {message}
        </p>
      )}
    </div>
  );
}

/**
 * Дописывает элементу ввода `aria-describedby` и `aria-invalid`.
 *
 * Иначе те же два атрибута пришлось бы повторить у каждого из четырнадцати полей — и у
 * пятнадцатого их бы не написали. Подсказка и сообщение об ошибке, не связанные с полем,
 * существуют только для того, кто их видит: программа чтения с экрана их не назовёт.
 */
function describe(children: ReactNode, described: string, invalid: boolean): ReactNode {
  if (!isValidElement(children)) return children;
  const extra: Record<string, unknown> = {};
  if (described !== '') extra['aria-describedby'] = described;
  if (invalid) extra['aria-invalid'] = true;
  return cloneElement(children, extra);
}
