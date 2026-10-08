/**
 * Взаимодействие — «кто кого ждёт: организации, письма, соглашения?» (ТЗ 2, 3.4).
 *
 * Четыре вкладки, вид — в адресе (`/interaction?view=`), как у Пульта и Ижро:
 *
 * - **Вопросы** — четыре вопроса ТЗ 5 с ответом и действием: кто нам не отвечает, на что
 *   мы должны ответить, как быстро отвечают (только при пяти письмах и больше), какие
 *   соглашения спят;
 * - **Письма** — архив писем в порядке лестницы: список на телефоне, таблица на ноутбуке;
 *   помощник вносит письмо и отмечает ответ, руководитель оценивает ответ одним касанием;
 * - **Организации** — кто нас ждёт и кого ждём мы; карточка собирает письма, поручения,
 *   проекты и соглашения (ТЗ 11);
 * - **Соглашения** — следующий шаг и его срок, «спящие».
 */

import { useNavigate, useSearch } from '@tanstack/react-router';
import { Users } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useDevice } from '@/app/device';
import { useCurrentUser } from '@/app/session';
import { describeError } from '@/shared/api/client';
import type { Role } from '@/shared/api/orbita';
import { cn } from '@/shared/lib/cn';
import { formatDateTime } from '@/shared/time';
import { Sheet } from '@/shared/ui/Sheet';
import { Failure, Loading } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';

import { AgreementsTab } from './AgreementsTab';
import { NO_FILTER, type Filter } from './filter';
import { LetterPanel } from './LetterPanel';
import { LettersTab } from './LettersTab';
import type { InteractionView } from './model';
import { OrganizationPanel } from './OrganizationPanel';
import { OrganizationsTab } from './OrganizationsTab';
import { QuestionsTab } from './QuestionsTab';
import { useInteraction } from './useInteraction';

const TABS = ['questions', 'letters', 'organizations', 'agreements'] as const;

export type Tab = (typeof TABS)[number];

function isTab(value: unknown): value is Tab {
  return TABS.some((each) => each === value);
}

/** Что открыто в листе: письмо или организация — у каждой своя карточка. */
export type Opened = { kind: 'letter'; id: string } | { kind: 'organization'; id: string };

export function InteractionSection() {
  const interaction = useInteraction();
  if (interaction.isPending) return <Loading />;
  if (interaction.isError) {
    return (
      <Failure
        detail={describeError(interaction.error)}
        onRetry={() => void interaction.refetch()}
      />
    );
  }
  return <Interaction view={interaction.data} />;
}

function Interaction({ view }: { view: InteractionView }) {
  const { t } = useTranslation();
  const device = useDevice();
  const user = useCurrentUser();
  // Роль подписывает действие, а не прячет данные (инвариант 13): оба видят всё.
  const viewer: Role = user.data?.role === 'leader' ? 'leader' : 'assistant';

  const search: { view?: unknown } = useSearch({ strict: false });
  const navigate = useNavigate();
  const tab: Tab = isTab(search.view) ? search.view : 'questions';
  const setTab = (next: Tab) =>
    void navigate({
      to: '/interaction',
      search: next === 'questions' ? {} : { view: next },
      replace: true,
    });

  const [filter, setFilter] = useState<Filter>(NO_FILTER);
  const [sleepingOnly, setSleepingOnly] = useState(false);
  const [open, setOpen] = useState<Opened | null>(null);

  const showLetters = (patch: Partial<Filter>) => {
    setFilter({ ...NO_FILTER, ...patch });
    setTab('letters');
  };

  const freshness = t('interaction.freshness', { when: formatDateTime(view.as_of) });

  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <Header view={view} compact={device === 'phone'}>
        <span
          role="tablist"
          aria-label={t('interaction.tabs.label')}
          className="inline-flex flex-wrap gap-1"
        >
          {TABS.map((each) => (
            <button
              key={each}
              type="button"
              role="tab"
              aria-selected={tab === each}
              onClick={() => {
                if (each === 'agreements') setSleepingOnly(false);
                setTab(each);
              }}
              className={cn(
                'min-h-touch rounded-[var(--radius-pill)] border px-3 text-xs font-medium',
                'transition-colors duration-[var(--motion-fast)]',
                tab === each
                  ? 'border-accent bg-accent text-ink-inverse'
                  : 'border-line bg-card text-ink hover:bg-hover',
              )}
            >
              {t(`interaction.tabs.${each}`)}
            </button>
          ))}
        </span>
      </Header>

      <div role="tabpanel" aria-label={t(`interaction.tabs.${tab}`)}>
        {tab === 'questions' ? (
          <QuestionsTab
            view={view}
            device={device}
            freshness={freshness}
            onLetters={showLetters}
            onOrganization={(id) => setOpen({ kind: 'organization', id })}
            onTab={(next) => {
              if (next === 'agreements') setSleepingOnly(true);
              setTab(next);
            }}
          />
        ) : tab === 'letters' ? (
          <LettersTab
            view={view}
            device={device}
            viewer={viewer}
            filter={filter}
            onFilter={setFilter}
            onOpen={(id) => setOpen({ kind: 'letter', id })}
          />
        ) : tab === 'organizations' ? (
          <OrganizationsTab
            view={view}
            device={device}
            onOpen={(id) => setOpen({ kind: 'organization', id })}
          />
        ) : (
          <AgreementsTab
            view={view}
            device={device}
            viewer={viewer}
            sleepingOnly={sleepingOnly}
            onSleepingOnly={setSleepingOnly}
            onOrganization={(id) => setOpen({ kind: 'organization', id })}
          />
        )}
      </div>

      {open ? (
        <Sheet
          label={t(
            open.kind === 'letter' ? 'interaction.letter.label' : 'interaction.organization.label',
          )}
          closeLabel={t('interaction.close')}
          onClose={() => setOpen(null)}
          wide
        >
          {open.kind === 'letter' ? (
            <LetterPanel
              view={view}
              id={open.id}
              viewer={viewer}
              onOrganization={(id) => setOpen({ kind: 'organization', id })}
            />
          ) : (
            <OrganizationPanel id={open.id} onLetter={(id) => setOpen({ kind: 'letter', id })} />
          )}
        </Sheet>
      ) : null}
    </div>
  );
}

function Header({
  view,
  compact,
  children,
}: {
  view: InteractionView;
  compact: boolean;
  children: React.ReactNode;
}) {
  const { t } = useTranslation();
  const demo = view.is_demo ? (
    <span title={t('pult.demoHint')}>
      <Signal state="wait">{t('pult.demo')}</Signal>
    </span>
  ) : null;

  if (compact) {
    return (
      <header className="flex flex-col gap-2">
        <h1 className="text-lg font-semibold text-ink-strong">{t('sections.interaction')}</h1>
        <p className="text-sm text-ink-muted">{t('sectionQuestions.interaction')}</p>
        {demo ? <p className="flex flex-wrap items-center gap-2 text-xs">{demo}</p> : null}
        {children}
      </header>
    );
  }

  return (
    <header className="flex flex-wrap items-center gap-4">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-[var(--radius)] bg-accent-soft text-accent-ink">
          <Users className="size-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-ink-strong">{t('sections.interaction')}</h1>
          <p className="text-sm text-ink-muted">{t('sectionQuestions.interaction')}</p>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
            <span>{t('pult.asOf', { when: formatDateTime(view.as_of) })}</span>
            {demo}
          </p>
        </div>
      </div>
      {children}
    </header>
  );
}
