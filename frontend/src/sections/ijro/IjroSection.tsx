/**
 * Ижро — «что на контроле, что горит, кто исполнитель, работает ли он, из-за кого
 * сорвётся» (ТЗ 2).
 *
 * Четыре вкладки, вид — в адресе (`/ijro?view=`), как у Пульта:
 *
 * - **Вопросы** — двенадцать вопросов с ответом числом и действием (ТЗ 5, V31). Действие
 *   ведёт в отфильтрованный список: тот же набор строк, что посчитан в ответе;
 * - **Поручения** — реестр в порядке лестницы: список на телефоне (ТЗ 6: без таблиц),
 *   таблица на ноутбуке и мониторе; касание открывает карточку;
 * - **Документы** — стена документов: как исполнен документ целиком;
 * - **Загрузка** — таблица Word, предпросмотр классов изменений, применение. Только
 *   помощник (V35): руководитель вкладку не видит.
 *
 * Справка по проблемным поручениям открывается вместо вкладки, а не листом: так её
 * печатает браузер — оболочка на печати скрыта, как у отчёта недели.
 */

import { useNavigate, useSearch } from '@tanstack/react-router';
import { FileText } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useDevice } from '@/app/device';
import { useCurrentUser } from '@/app/session';
import { describeError } from '@/shared/api/client';
import type { Role } from '@/shared/api/orbita';
import { cn } from '@/shared/lib/cn';
import { formatDate, formatDateTime } from '@/shared/time';
import { Sheet } from '@/shared/ui/Sheet';
import { Failure, Loading } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';

import { AssignmentPanel } from './AssignmentPanel';
import { AssignmentsTab } from './AssignmentsTab';
import { DocumentsTab } from './DocumentsTab';
import { NO_FILTER, type Filter } from './filter';
import type { IjroView } from './model';
import { QuestionsTab } from './QuestionsTab';
import { Spravka } from './Spravka';
import { UploadTab } from './UploadTab';
import { useIjro } from './useIjro';

const TABS = ['questions', 'assignments', 'documents', 'upload'] as const;

export type Tab = (typeof TABS)[number];

function isTab(value: unknown): value is Tab {
  return TABS.some((each) => each === value);
}

export function IjroSection() {
  const ijro = useIjro();
  if (ijro.isPending) return <Loading />;
  if (ijro.isError) {
    return <Failure detail={describeError(ijro.error)} onRetry={() => void ijro.refetch()} />;
  }
  return <Ijro view={ijro.data} />;
}

function Ijro({ view }: { view: IjroView }) {
  const { t } = useTranslation();
  const device = useDevice();
  const user = useCurrentUser();
  // Роль подписывает действие, а не прячет данные (инвариант 13): оба видят всё, кнопки —
  // по роли. Сервер проверит то же сам.
  const viewer: Role = user.data?.role === 'leader' ? 'leader' : 'assistant';
  const tabs = TABS.filter((each) => each !== 'upload' || viewer === 'assistant');

  const search: { view?: unknown } = useSearch({ strict: false });
  const navigate = useNavigate();
  const wanted = isTab(search.view) ? search.view : 'questions';
  const tab: Tab = tabs.includes(wanted) ? wanted : 'questions';
  const setTab = (next: Tab) =>
    void navigate({
      to: '/ijro',
      search: next === 'questions' ? {} : { view: next },
      replace: true,
    });

  const [filter, setFilter] = useState<Filter>(NO_FILTER);
  const [open, setOpen] = useState<string | null>(null);
  const [spravka, setSpravka] = useState(false);

  const showList = (patch: Partial<Filter>) => {
    setFilter({ ...NO_FILTER, ...patch });
    setTab('assignments');
  };

  const freshness = view.table_on
    ? t('ijro.freshness', { date: formatDate(view.table_on) })
    : t('ijro.noTable');

  return (
    <div className="flex flex-col gap-4 lg:gap-5">
      <Header view={view} compact={device === 'phone'} freshness={freshness}>
        <span
          role="tablist"
          aria-label={t('ijro.tabs.label')}
          className="inline-flex flex-wrap gap-1"
        >
          {tabs.map((each) => (
            <button
              key={each}
              type="button"
              role="tab"
              aria-selected={tab === each}
              onClick={() => {
                setSpravka(false);
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
              {t(`ijro.tabs.${each}`)}
            </button>
          ))}
        </span>
      </Header>

      <div role="tabpanel" aria-label={t(`ijro.tabs.${tab}`)}>
        {spravka ? (
          <Spravka view={view} freshness={freshness} onBack={() => setSpravka(false)} />
        ) : tab === 'questions' ? (
          <QuestionsTab
            view={view}
            device={device}
            viewer={viewer}
            freshness={freshness}
            onList={showList}
            onTab={setTab}
            onSpravka={() => setSpravka(true)}
          />
        ) : tab === 'assignments' ? (
          <AssignmentsTab
            view={view}
            device={device}
            viewer={viewer}
            filter={filter}
            onFilter={setFilter}
            onOpen={setOpen}
          />
        ) : tab === 'documents' ? (
          <DocumentsTab
            view={view}
            device={device}
            freshness={freshness}
            onDocument={(document) => showList({ document })}
            onOpen={setOpen}
          />
        ) : (
          <UploadTab view={view} />
        )}
      </div>

      {open ? (
        <Sheet
          label={t('ijro.card.label')}
          closeLabel={t('ijro.card.close')}
          onClose={() => setOpen(null)}
          wide
        >
          <AssignmentPanel id={open} viewer={viewer} />
        </Sheet>
      ) : null}
    </div>
  );
}

function Header({
  view,
  compact,
  freshness,
  children,
}: {
  view: IjroView;
  compact: boolean;
  freshness: string;
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
      <header className="flex flex-col gap-2 print:hidden">
        <h1 className="text-lg font-semibold text-ink-strong">{t('sections.ijro')}</h1>
        <p className="text-sm text-ink-muted">{t('sectionQuestions.ijro')}</p>
        <p className="flex flex-wrap items-center gap-2 text-xs text-ink-muted">
          <span>{freshness}</span>
          {demo}
        </p>
        {children}
      </header>
    );
  }

  return (
    <header className="flex flex-wrap items-center gap-4 print:hidden">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-[var(--radius)] bg-accent-soft text-accent-ink">
          <FileText className="size-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-ink-strong">{t('sections.ijro')}</h1>
          <p className="text-sm text-ink-muted">{t('sectionQuestions.ijro')}</p>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
            <span>{t('pult.asOf', { when: formatDateTime(view.as_of) })}</span>
            <span>{freshness}</span>
            {demo}
          </p>
        </div>
      </div>
      {children}
    </header>
  );
}
