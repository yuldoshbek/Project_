/**
 * Вкладка «Организации»: кто нас ждёт и кого ждём мы (ТЗ 2, 3.4).
 *
 * Порядок задаёт сервер: сначала те, где есть неотвеченное, затем по названию. Скорость
 * ответа — медианой только при пяти письмах с ответом и больше, иначе честное «мало писем»
 * (ТЗ 4, критерий 4 блока 2). Центр подписан как учреждённый агентством (ТЗ 3.4).
 */

import { useTranslation } from 'react-i18next';

import type { Device } from '@/app/device';
import { cn } from '@/shared/lib/cn';
import { Signal } from '@/shared/ui/Signal';

import type { InteractionView } from './model';
import { speedText } from './text';

export function OrganizationsTab({
  view,
  device,
  onOpen,
}: {
  view: InteractionView;
  device: Device;
  onOpen: (id: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <ul
      className={cn(
        'grid gap-2',
        device === 'phone' ? 'grid-cols-1' : 'grid-cols-2 gap-3',
        device === 'monitor' && 'grid-cols-4 gap-4',
      )}
    >
      {view.organizations.map((row) => (
        <li key={row.id} className="min-w-0 rounded-[var(--radius-lg)] border border-line bg-card">
          <button
            type="button"
            onClick={() => onOpen(row.id)}
            className="flex min-h-touch w-full flex-col gap-2 p-4 text-left"
          >
            <span className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <span className="font-semibold text-ink-strong">{row.short_name ?? row.name}</span>
              <span className="text-xs text-ink-muted">
                {row.is_founded_by_agency
                  ? t('interaction.organizations.center')
                  : t(`interaction.kinds.${row.kind}`)}
              </span>
            </span>
            {row.short_name ? (
              <span className="line-clamp-1 text-xs text-ink-muted">{row.name}</span>
            ) : null}
            <span className="flex flex-wrap gap-2">
              {row.to_answer > 0 ? (
                <Signal state="burn">
                  {t('interaction.organizations.toAnswer', { count: row.to_answer })}
                </Signal>
              ) : null}
              {row.waiting > 0 ? (
                <Signal state="wait">
                  {t('interaction.organizations.waiting', { count: row.waiting })}
                </Signal>
              ) : null}
              {row.overdue_steps > 0 ? (
                <Signal state="burn">
                  {t('interaction.organizations.overdueSteps', { count: row.overdue_steps })}
                </Signal>
              ) : null}
              {row.sleeping > 0 ? (
                <Signal state="wait">
                  {t('interaction.organizations.sleeping', { count: row.sleeping })}
                </Signal>
              ) : null}
              {row.to_answer + row.waiting + row.sleeping + row.overdue_steps === 0 ? (
                <Signal state="calm">{t('interaction.organizations.calm')}</Signal>
              ) : null}
            </span>
            <span className="numeric text-xs text-ink-muted">
              {[
                speedText(t, row),
                row.agreement_count > 0
                  ? t('interaction.organizations.agreements', { count: row.agreement_count })
                  : null,
                row.ijro_lead > 0
                  ? t('interaction.organizations.ijro', { count: row.ijro_lead })
                  : null,
                row.project_count > 0
                  ? t('interaction.organizations.projects', { count: row.project_count })
                  : null,
              ]
                .filter(Boolean)
                .join(' · ')}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
