/**
 * Управление — раздел помощника (CONTEXT, ТЗ 1.2): обход, справочники, пороги, доступ.
 *
 * Критерий ТЗ 11: справочники редактируются; пороги меняют поведение сигналов; ссылки
 * перевыпускаются; обход. Вкладка — один вопрос, и открывается сразу нужная: помощнику —
 * обход недели, руководителю — пороги. Руководитель смотрит справочники и пороги без
 * правки; обход и доступ ведёт помощник (API доступа отвечает руководителю отказом).
 *
 * Экран на вымышленных данных (`demo.ts`) — до утверждения; устройства и перевыпуск
 * ссылок — уже настоящий API блока 0.
 */

import { Settings } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useDevice } from '@/app/device';
import { useCurrentUser } from '@/app/session';
import { describeError } from '@/shared/api/client';
import { cn } from '@/shared/lib/cn';
import { formatDateTime } from '@/shared/time';
import { Signal } from '@/shared/ui/Signal';
import { Failure, Loading } from '@/shared/ui/States';

import { AccessTab } from './AccessTab';
import { DictionariesTab } from './DictionariesTab';
import { TABS, type ManagementView, type Tab } from './model';
import { RoundTab } from './RoundTab';
import { ThresholdsTab } from './ThresholdsTab';
import { useManagement } from './useManagement';

const LEADER_TABS: readonly Tab[] = ['thresholds', 'dictionaries'];

export function ManagementSection() {
  const management = useManagement();
  if (management.isPending) return <Loading />;
  if (management.isError) {
    return (
      <Failure detail={describeError(management.error)} onRetry={() => void management.refetch()} />
    );
  }
  return <Management view={management.data} />;
}

function Management({ view }: { view: ManagementView }) {
  const { t } = useTranslation();
  const device = useDevice();
  const user = useCurrentUser();
  const isPhone = device === 'phone';
  const canEdit = user.data?.can_write === true;
  const tabs = canEdit ? TABS : LEADER_TABS;
  const [chosen, setTab] = useState<Tab | null>(null);
  const tab = chosen && tabs.includes(chosen) ? chosen : tabs[0]!;

  return (
    <div className={cn('flex flex-col', isPhone ? 'gap-3' : 'gap-5')}>
      <header className="flex items-center gap-3">
        {isPhone ? null : (
          <span className="grid size-10 shrink-0 place-items-center rounded-[var(--radius)] bg-accent-soft text-accent-ink">
            <Settings className="size-5" aria-hidden="true" />
          </span>
        )}
        <div className="min-w-0">
          <h1 className={cn('font-semibold text-ink-strong', isPhone ? 'text-lg' : 'text-xl')}>
            {t('management.title')}
          </h1>
          <p className="text-sm text-ink-muted">{t('sectionQuestions.management')}</p>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
            <span>{t('pult.asOf', { when: formatDateTime(view.as_of) })}</span>
            {view.is_demo ? (
              <span title={t('pult.demoHint')}>
                <Signal state="wait">{t('pult.demo')}</Signal>
              </span>
            ) : null}
          </p>
        </div>
      </header>

      {canEdit ? null : <p className="text-sm text-ink-muted">{t('management.leaderNote')}</p>}

      {/* На телефоне — сеткой два на два: в строку четыре вкладки не влезают, и перенос
          одной выглядел бы случайным. */}
      <span
        role="tablist"
        aria-label={t('management.tabs.label')}
        className={cn('gap-1.5', isPhone ? 'grid grid-cols-2' : 'flex flex-wrap')}
      >
        {tabs.map((each) => (
          <button
            key={each}
            type="button"
            role="tab"
            aria-selected={tab === each}
            onClick={() => setTab(each)}
            className={cn(
              'inline-flex min-h-touch items-center justify-center gap-1.5 rounded-[var(--radius-pill)] border px-3.5 text-sm font-medium',
              'transition-colors duration-[var(--motion-fast)]',
              tab === each
                ? 'border-accent bg-accent text-ink-inverse'
                : 'border-line bg-card text-ink hover:bg-hover',
            )}
          >
            {t(`management.tabs.${each}`)}
            {each === 'round' && view.round.items.length > 0 ? (
              <span
                className={cn(
                  'numeric rounded-[var(--radius-pill)] px-1.5 text-xs',
                  tab === each ? 'bg-ink-inverse/10' : 'bg-sunken text-ink-muted',
                )}
              >
                {view.round.items.length}
              </span>
            ) : null}
          </button>
        ))}
      </span>

      <div role="tabpanel" aria-label={t(`management.tabs.${tab}`)}>
        {tab === 'round' ? (
          <RoundTab round={view.round} people={view.people} compact={isPhone} />
        ) : tab === 'thresholds' ? (
          <ThresholdsTab
            thresholds={view.thresholds}
            canEdit={canEdit}
            wide={!isPhone}
            demo={view.is_demo}
          />
        ) : tab === 'dictionaries' ? (
          <DictionariesTab
            groups={view.dictionaries}
            templates={view.templates}
            canEdit={canEdit}
            compact={isPhone}
          />
        ) : (
          <AccessTab links={view.links} device={device} />
        )}
      </div>
    </div>
  );
}
