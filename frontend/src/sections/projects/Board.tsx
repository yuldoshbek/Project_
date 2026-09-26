/**
 * Доска: колонки — статусы проекта, плитку можно перетащить в соседнюю колонку.
 *
 * Перетаскивание — ускорение, а не единственный путь: статус меняется и в карточке
 * проекта, кнопками. Перетаскивание не работает с клавиатуры и на части сенсорных
 * экранов, и завязанное только на него действие для них бы исчезло.
 *
 * Пауза и отмена требуют причины (ТЗ 3.1): перенос в эти колонки не меняет статус сразу,
 * а просит причину — её спрашивает `ProjectsSection`.
 */

import { useState, type DragEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/shared/lib/cn';

import { BOARD_COLUMNS, type ProjectCard, type ProjectStatus } from './model';
import { ProjectTile } from './ProjectTile';

interface BoardProps {
  items: ProjectCard[];
  onOpen: (id: string) => void;
  onMove: (id: string, status: ProjectStatus) => void;
  /**
   * Монитор: «В работе» — двойной ширины, плитки в два ряда. В ней почти все проекты, и
   * четыре равные колонки на 2560 px дали бы одну длинную ленту и три пустых.
   */
  wide?: boolean;
}

export function Board({ items, onOpen, onMove, wide = false }: BoardProps) {
  const { t } = useTranslation();
  const [over, setOver] = useState<ProjectStatus | null>(null);

  const drop = (status: ProjectStatus) => (event: DragEvent) => {
    event.preventDefault();
    setOver(null);
    const id = event.dataTransfer.getData('text/plain');
    const card = items.find((each) => each.id === id);
    if (card && card.status !== status) onMove(id, status);
  };

  return (
    <div
      className={cn('grid items-start gap-3', wide ? 'grid-cols-[2fr_1fr_1fr_1fr]' : 'grid-cols-4')}
    >
      {BOARD_COLUMNS.map((status) => {
        const column = items.filter((card) => card.status === status);
        return (
          <section
            key={status}
            aria-label={t(`projects.statuses.${status}`)}
            onDragOver={(event) => {
              event.preventDefault();
              setOver(status);
            }}
            onDragLeave={() => setOver(null)}
            onDrop={drop(status)}
            className={cn(
              'flex min-h-40 min-w-0 flex-col gap-2 rounded-[var(--radius-lg)] border p-2',
              'transition-colors duration-[var(--motion-fast)]',
              over === status ? 'border-line-accent bg-accent-soft/40' : 'border-line bg-sunken',
            )}
          >
            <header className="flex items-baseline justify-between px-1 pt-1">
              <h2 className="text-sm font-semibold text-ink-strong">
                {t(`projects.statuses.${status}`)}
              </h2>
              <span className="numeric text-xs text-ink-muted">{column.length}</span>
            </header>
            {column.length === 0 ? (
              <p className="px-1 py-4 text-center text-xs text-ink-muted">
                {over === status ? t('projects.board.drop') : t('projects.board.empty')}
              </p>
            ) : (
              <div
                className={cn(
                  'grid gap-2',
                  wide && status === 'in_progress' ? 'grid-cols-2' : 'grid-cols-1',
                )}
              >
                {column.map((card) => (
                  <ProjectTile key={card.id} card={card} onOpen={onOpen} draggable />
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
