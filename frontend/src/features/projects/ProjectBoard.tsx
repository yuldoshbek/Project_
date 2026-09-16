/**
 * Доска проектов (ORB-019).
 *
 * Тот же портфель, что и в списке, — те же фильтры из адреса, те же данные, — разложенный
 * по статусам. Колонки берутся из справочника, а не из кода: названия и порядок статусов —
 * редактируемые данные (ТЗ 6.8), и доска, перечислившая их у себя, разошлась бы со
 * справочником при первой же правке.
 *
 * **Перенести можно двумя способами, и второй не запасной.** Карточку перетаскивают мышью
 * или пальцем (ТЗ 6.1) — либо выбирают колонку в поле на самой карточке. Второе — требование
 * доступности, а не удобство: перетаскивание недоступно с клавиатуры и программе чтения с
 * экрана, и у действия, которое делается перетаскиванием, обязана быть замена обычным
 * выбором (WCAG 2.2, критерий 2.5.7). Заодно это путь для телефона, где перетаскивание
 * спорит с прокруткой доски.
 *
 * **Порядка внутри колонки нет.** Карточки идут так, как их отдал сервер. Поле позиции есть
 * у задач (ORB-021); у проектов его нет, и заводить его ради перестановки внутри колонки
 * критерий не требует (CLAUDE.md: полей «на будущее» не добавлять).
 *
 * Руководителю доска открывается только для чтения (ADR-0011): решение по проекту «На
 * контроле» — отдельное действие (ORB-062), а не перетаскивание.
 */

import type { Announcements, DragEndEvent, DragStartEvent } from '@dnd-kit/core';
import {
  DndContext,
  DragOverlay,
  MouseSensor,
  TouchSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import type { SyntheticEvent } from 'react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { formatDate } from '../../shared/time';
import { cx } from '../../shared/ui/cx';
import { HealthDot } from '../../shared/ui/HealthDot';
import { AttachmentsButton } from '../documents/AttachmentsDrawer';
import type { Dictionaries, Project, ProjectStatusEntry } from './api';
import { localizedName } from './api';
import styles from './board.module.css';
import { ReasonDialog } from './ReasonDialog';

export interface ProjectBoardProps {
  projects: Project[];
  dictionaries: Dictionaries;
  mayEdit: boolean;
  onMove: (project: Project, status: string, reason?: string) => void;
  onOpenFiles: (project: Project) => void;
}

/** Нажатие на поле или кнопку внутри карточки не должно начинать перетаскивание. */
const keepToControl = (event: SyntheticEvent) => {
  event.stopPropagation();
};

export function ProjectBoard({
  projects,
  dictionaries,
  mayEdit,
  onMove,
  onOpenFiles,
}: ProjectBoardProps) {
  const { t, i18n } = useTranslation();
  const [dragged, setDragged] = useState<Project | null>(null);
  const [asking, setAsking] = useState<{ project: Project; status: ProjectStatusEntry } | null>(
    null,
  );

  // Мышь — после сдвига на несколько пикселей: иначе щелчок по карточке начинал бы
  // перенос. Палец — после удержания: иначе прокрутить доску, коснувшись карточки, стало бы
  // нельзя, а на телефоне к карточке касаются почти всегда.
  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 8 } }),
  );

  const statuses = dictionaries.project_statuses;
  const nameOf = (code: string) => {
    const entry = statuses.find((item) => item.code === code);
    return entry === undefined ? code : localizedName(entry.name, i18n.language);
  };
  const projectOf = (id: string | number) => projects.find((item) => item.id === String(id));

  const move = (project: Project, code: string) => {
    if (project.status_code === code) return;
    const target = statuses.find((item) => item.code === code);
    if (target === undefined) return;
    if (target.requires_reason) setAsking({ project, status: target });
    else onMove(project, code);
  };

  const onDragStart = ({ active }: DragStartEvent) => {
    setDragged(projectOf(active.id) ?? null);
  };

  const onDragEnd = ({ active, over }: DragEndEvent) => {
    setDragged(null);
    const project = projectOf(active.id);
    if (project !== undefined && over !== null) move(project, String(over.id));
  };

  // Объявления для программы чтения с экрана. Без них библиотека говорит по-английски, а
  // это посреди русского интерфейса хуже молчания.
  const announcements: Announcements = {
    onDragStart: ({ active }) =>
      t('projects.board.announceStart', { title: projectOf(active.id)?.title ?? '' }),
    onDragOver: ({ over }) =>
      over === null
        ? undefined
        : t('projects.board.announceOver', { status: nameOf(String(over.id)) }),
    onDragEnd: ({ active, over }) =>
      over === null
        ? t('projects.board.announceCancel')
        : t('projects.board.announceEnd', {
            title: projectOf(active.id)?.title ?? '',
            status: nameOf(String(over.id)),
          }),
    onDragCancel: () => t('projects.board.announceCancel'),
  };

  return (
    <>
      <DndContext
        sensors={sensors}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
        onDragCancel={() => {
          setDragged(null);
        }}
        accessibility={{
          announcements,
          screenReaderInstructions: { draggable: t('projects.board.dragHint') },
        }}
      >
        <div className={styles.board}>
          {statuses.map((status) => {
            const inColumn = projects.filter((project) => project.status_code === status.code);
            return (
              <Column
                key={status.code}
                code={status.code}
                name={localizedName(status.name, i18n.language)}
                count={inColumn.length}
                droppable={mayEdit}
              >
                {inColumn.map((project) => (
                  <li key={project.id}>
                    <Card
                      project={project}
                      dictionaries={dictionaries}
                      mayEdit={mayEdit}
                      onMove={move}
                      onOpenFiles={onOpenFiles}
                    />
                  </li>
                ))}
              </Column>
            );
          })}
        </div>

        {/* Карточка под курсором рисуется отдельно от колонок: внутри колонки её обрезала
            бы прокрутка доски, и тащить пришлось бы невидимое. */}
        <DragOverlay>
          {dragged !== null && (
            <div className={cx(styles.card, styles.lifted)}>
              <CardBody project={dragged} dictionaries={dictionaries} />
            </div>
          )}
        </DragOverlay>
      </DndContext>

      {asking !== null && (
        <ReasonDialog
          project={asking.project}
          statusName={localizedName(asking.status.name, i18n.language)}
          onCancel={() => {
            setAsking(null);
          }}
          onConfirm={(reason) => {
            onMove(asking.project, asking.status.code, reason);
            setAsking(null);
          }}
        />
      )}
    </>
  );
}

function Column({
  code,
  name,
  count,
  droppable,
  children,
}: {
  code: string;
  name: string;
  count: number;
  droppable: boolean;
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  const { setNodeRef, isOver } = useDroppable({ id: code, disabled: !droppable });

  return (
    <section
      ref={setNodeRef}
      className={cx(styles.column, isOver && styles.over)}
      aria-label={name}
    >
      <header className={styles.columnHead}>
        <h2 className={styles.columnTitle}>{name}</h2>
        <span className={styles.columnCount}>{count}</span>
      </header>
      {count === 0 ? (
        <p className={styles.empty}>{t('projects.board.empty')}</p>
      ) : (
        <ul className={styles.cards}>{children}</ul>
      )}
    </section>
  );
}

function Card({
  project,
  dictionaries,
  mayEdit,
  onMove,
  onOpenFiles,
}: {
  project: Project;
  dictionaries: Dictionaries;
  mayEdit: boolean;
  onMove: (project: Project, status: string) => void;
  onOpenFiles: (project: Project) => void;
}) {
  const { t, i18n } = useTranslation();
  const { setNodeRef, listeners, isDragging } = useDraggable({
    id: project.id,
    disabled: !mayEdit,
  });

  // Атрибуты перетаскивания (роль кнопки, подсказка «нажмите пробел») на карточку не
  // навешиваются: с клавиатуры карточку переносят полем «Перенести в колонку», и обещать
  // программе чтения с экрана перенос пробелом значило бы обещать то, чего нет.
  return (
    <article
      ref={setNodeRef}
      {...(mayEdit ? listeners : undefined)}
      className={cx(styles.card, mayEdit && styles.grab, isDragging && styles.dragging)}
    >
      <CardBody project={project} dictionaries={dictionaries} />

      <div className={styles.cardFoot}>
        {mayEdit && (
          <label className={styles.move} onMouseDown={keepToControl} onTouchStart={keepToControl}>
            <span className={styles.srOnly}>{t('projects.board.moveLabel')}</span>
            <select
              className={styles.moveSelect}
              value={project.status_code}
              onChange={(event) => {
                onMove(project, event.target.value);
              }}
            >
              {dictionaries.project_statuses.map((status) => (
                <option key={status.code} value={status.code}>
                  {localizedName(status.name, i18n.language)}
                </option>
              ))}
            </select>
          </label>
        )}
        <span onMouseDown={keepToControl} onTouchStart={keepToControl}>
          <AttachmentsButton
            label={t('documents.open', { name: project.title })}
            onOpen={() => {
              onOpenFiles(project);
            }}
          />
        </span>
      </div>
    </article>
  );
}

/**
 * Содержимое карточки — по эталону дизайн-системы (`design/Components.dc.html`): номер и
 * название, светофор с подписью, приоритет и направление, доля выполненного, срок, строка
 * «что мешает». Куратора, ближайшей вехи и числа просроченных задач в списке портфеля нет —
 * их нет и в ответе, и тянуть их ради карточки значило бы по запросу на проект.
 */
function CardBody({ project, dictionaries }: { project: Project; dictionaries: Dictionaries }) {
  const { t, i18n } = useTranslation();

  const priority = dictionaries.priorities.find((item) => item.code === project.priority_code);
  const direction = dictionaries.directions.find((item) => item.id === project.direction_id);
  const status = dictionaries.project_statuses.find((item) => item.code === project.status_code);

  return (
    <>
      <div className={styles.cardHead}>
        <div className={styles.cardName}>
          <span className={styles.code}>{project.code}</span>
          <span className={styles.title}>{project.title}</span>
        </div>
        <HealthDot health={project.health} label={t(`health.${project.health}`)} />
      </div>

      <div className={styles.chips}>
        {priority !== undefined && (
          <span className={cx(styles.chip, styles[`priority_${project.priority_code}`])}>
            {localizedName(priority.name, i18n.language)}
          </span>
        )}
        {direction !== undefined && (
          <span className={styles.chip}>{localizedName(direction.name, i18n.language)}</span>
        )}
      </div>

      <div className={styles.progress}>
        <div className={styles.row}>
          <span className={styles.muted}>{t('projects.columnProgress')}</span>
          <span className={styles.number}>
            {t('projects.board.percent', { value: project.progress_pct })}
          </span>
        </div>
        <div
          className={styles.track}
          role="progressbar"
          aria-valuenow={project.progress_pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={t('projects.columnProgress')}
        >
          <div className={styles.fill} style={{ width: `${String(project.progress_pct)}%` }} />
        </div>
      </div>

      <div className={styles.row}>
        <span className={styles.muted}>{t('projects.columnDue')}</span>
        <span className={styles.number}>{formatDate(project.due_on)}</span>
      </div>

      {/* Причина паузы и отмены — ровно то, что нужно прочитать на этой карточке: без неё
          «Приостановлен» не отвечает на вопрос «чего ждём». */}
      {status?.requires_reason === true && project.status_reason !== null && (
        <p className={styles.reasonShown}>
          {t('projects.board.reasonShown', { reason: project.status_reason })}
        </p>
      )}

      {project.impediment !== null && (
        <p
          className={cx(
            styles.impediment,
            project.impediment_is_active ? styles.impedimentActive : styles.impedimentStale,
          )}
          title={project.impediment}
        >
          {project.impediment}
        </p>
      )}
    </>
  );
}
