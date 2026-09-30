/**
 * Вкладка «Документы» — стена документов: «как исполнен документ целиком?» (ТЗ 5).
 *
 * Один документ — одна карточка: сколько пунктов сдано, клетка на каждый пункт в цвете его
 * ступени и кого вызвать с отчётом — у кого больше всего открытых пунктов. Клетка открывает
 * карточку поручения, документ — его пункты в реестре.
 */

import { useTranslation } from 'react-i18next';

import type { Device } from '@/app/device';
import { STEP_SIGNAL } from '@/sections/pult/model';
import { cn } from '@/shared/lib/cn';
import { formatDate } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';
import { Signal } from '@/shared/ui/Signal';

import { OPEN_STAGES, type IjroView, type WallCell } from './model';

const CELL = {
  burn: 'bg-burn',
  wait: 'bg-wait',
  call: 'bg-call',
} as const;

function cellColor(cell: WallCell): string {
  if (cell.step) return CELL[STEP_SIGNAL[cell.step]];
  // Сданное и снятое с контроля — сделано; открытое без ступени — идёт по плану.
  return OPEN_STAGES.has(cell.stage) ? 'bg-ink-muted/40' : 'bg-calm';
}

interface DocumentsTabProps {
  view: IjroView;
  device: Device;
  freshness: string;
  onDocument: (id: string) => void;
  onOpen: (id: string) => void;
}

export function DocumentsTab({ view, device, freshness, onDocument, onOpen }: DocumentsTabProps) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-3">
      {/* Цвет клетки — словами: одним цветом состояние не передаётся (см. `Signal`). */}
      <ul className="flex flex-wrap gap-2" aria-label={t('ijro.wall.legend.label')}>
        <li>
          <Signal state="calm">{t('ijro.wall.legend.done')}</Signal>
        </li>
        <li>
          <Signal state="burn">{t('ijro.wall.legend.burn')}</Signal>
        </li>
        <li>
          <Signal state="wait">{t('ijro.wall.legend.wait')}</Signal>
        </li>
        <li>
          <Signal state="call">{t('ijro.wall.legend.call')}</Signal>
        </li>
        <li>
          <Signal state="plain">{t('ijro.wall.legend.plan')}</Signal>
        </li>
      </ul>
      <div
        className={cn(
          'grid gap-3',
          device === 'phone'
            ? 'grid-cols-1'
            : device === 'monitor'
              ? 'grid-cols-3 gap-5'
              : 'grid-cols-2 gap-4',
        )}
      >
        {view.documents.map((wall) => (
          <Card
            key={wall.document.id}
            title={t('ijro.wall.title', {
              code: wall.document.code,
              date: formatDate(wall.document.issued_on),
            })}
            question={t('ijro.wall.question')}
            freshness={freshness}
            action={
              <Button size="small" onClick={() => onDocument(wall.document.id)}>
                {t('ijro.wall.open')}
              </Button>
            }
          >
            <p className="text-sm leading-snug text-ink">{wall.document.title}</p>
            <p className="numeric mt-3 text-lg font-semibold text-ink-strong">
              {t('ijro.wall.done', { done: wall.done, total: wall.total })}
            </p>
            <ul className="mt-2 flex flex-wrap gap-1" aria-label={t('ijro.wall.cells')}>
              {wall.cells.map((cell) => (
                <li key={cell.id}>
                  {/* Клетка — цель нажатия 44 px, цветной квадрат внутри меньше: иначе на
                    телефоне по пункту не попасть. */}
                  <button
                    type="button"
                    onClick={() => onOpen(cell.id)}
                    aria-label={t('ijro.wall.cell', {
                      band: cell.band ?? '',
                      state: cell.step
                        ? t(`pult.steps.${cell.step}`)
                        : t(`ijro.stages.${cell.stage}`),
                    })}
                    title={cell.band ?? undefined}
                    className="grid size-11 place-items-center md:size-8"
                  >
                    <span className={cn('size-6 rounded-[var(--radius-sm)]', cellColor(cell))} />
                  </button>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-sm text-ink-muted">
              {wall.call_for_report
                ? t('ijro.wall.call', {
                    name: wall.call_for_report.person.name,
                    open: wall.call_for_report.open,
                  })
                : t('ijro.wall.nobody')}
            </p>
          </Card>
        ))}
      </div>
    </div>
  );
}
