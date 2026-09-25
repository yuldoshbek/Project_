/**
 * Управление — единственный раздел, который работает с настоящими данными в блоке 0.
 *
 * Карточки, каждая отвечает на свой вопрос:
 *
 * - **Ссылки доступа** — «кто может войти и как закрыть доступ». Здесь же видно устройства:
 *   лишняя строка означает чужой вход. Только у помощника (ТЗ 2, `can_write` из `/api/me`):
 *   руководителю API на эти запросы отвечает 403, и вместо кнопок и списков, которые
 *   кончаются отказом, он видит одну строку о том, кто ведёт доступ.
 * - **Справочники** — «наполнена ли система». Это критерий приёмки блока: в рабочей базе
 *   справочники заведены, в демо — вымышленные данные.
 * - **Состояние** — «что именно выложено». Коммит из `/api/health` отвечает на вопрос,
 *   который иначе выясняется по поведению системы.
 *
 * Каждая карточка стоит в своей границе ошибок: упавшая при отрисовке показывает отказ на
 * своём месте, соседние продолжают работать.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy, KeyRound, RefreshCw } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useCurrentUser, useHealth } from '@/app/session';
import { describeError } from '@/shared/api/client';
import {
  api,
  type AccessLink,
  type Dictionaries,
  type DictionaryEntry,
  type Role,
} from '@/shared/api/orbita';
import { dictionariesQuery, sessionsQuery } from '@/shared/api/queries';
import { formatDateTime, formatSince } from '@/shared/time';
import { CardBoundary } from '@/shared/ui/Boundary';
import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';
import { Empty, Failure, Loading } from '@/shared/ui/States';

const ROLES: readonly Role[] = ['assistant', 'leader'];

/** Плитки справочников — в порядке ТЗ 3.9: сначала типы, затем места, затем статусы. */
const DICTIONARY_TILES = [
  { field: 'project_types', label: 'management.dictionaries.projectTypes' },
  { field: 'task_types', label: 'management.dictionaries.taskTypes' },
  { field: 'directions', label: 'management.dictionaries.directions' },
  { field: 'regions', label: 'management.dictionaries.regions' },
  { field: 'project_statuses', label: 'management.dictionaries.projectStatuses' },
  { field: 'task_statuses', label: 'management.dictionaries.taskStatuses' },
] as const satisfies readonly { field: keyof Dictionaries; label: string }[];

function LinkCard({ role }: { role: Role }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [issued, setIssued] = useState<AccessLink | null>(null);
  const [copied, setCopied] = useState(false);

  const sessions = useQuery(sessionsQuery(role));

  const reissue = useMutation({
    mutationFn: () => api.reissueLink(role),
    onSuccess: async (link) => {
      setIssued(link);
      setCopied(false);
      // Сессии гаснут вместе с перевыпуском — список устройств обязан это показать сразу,
      // иначе кнопка выглядит не сработавшей.
      await client.invalidateQueries({ queryKey: sessionsQuery(role).queryKey });
    },
  });

  return (
    <Card
      title={t(`role.${role}`)}
      question={t('management.links.body')}
      action={
        <Button
          look="primary"
          size="small"
          onClick={() => reissue.mutate()}
          disabled={reissue.isPending}
        >
          <RefreshCw className="size-4" />
          {t('management.links.reissue')}
        </Button>
      }
    >
      {reissue.isError ? <Failure detail={describeError(reissue.error)} /> : null}

      {issued ? (
        <div className="mb-4 rounded-[var(--radius)] border border-line-accent bg-accent-soft p-3">
          <p className="mb-2 text-xs text-accent-ink">{t('management.links.warning')}</p>
          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded-[var(--radius-sm)] bg-card px-2 py-1.5 text-xs">
              {issued.url}
            </code>
            <Button
              size="small"
              onClick={() => {
                void navigator.clipboard.writeText(issued.url).then(() => setCopied(true));
              }}
            >
              <Copy className="size-4" />
              {copied ? t('management.links.copied') : t('management.links.copy')}
            </Button>
          </div>
          <p className="mt-2 text-xs text-accent-ink">
            {t('management.links.issued', { when: formatDateTime(issued.issued_at) })}
          </p>
        </div>
      ) : null}

      <h3 className="mb-2 text-sm font-medium text-ink-strong">{t('management.links.devices')}</h3>

      {sessions.isPending ? <Loading /> : null}
      {sessions.isError ? <Failure detail={describeError(sessions.error)} /> : null}
      {sessions.data?.length === 0 ? <Empty label={t('management.links.noDevices')} /> : null}

      {sessions.data && sessions.data.length > 0 ? (
        <ul className="flex flex-col gap-2">
          {sessions.data.map((device, index) => (
            <li
              key={`${device.user_agent ?? 'device'}-${index}`}
              className="flex flex-wrap items-baseline justify-between gap-2 rounded-[var(--radius)] bg-sunken px-3 py-2"
            >
              {/* w-full вместе с truncate: без явной ширины элемент с длинной строкой
                  браузера сохраняет свою полную ширину и растягивает карточку. */}
              <span className="w-full min-w-0 truncate text-sm text-ink">
                {device.user_agent ?? t('management.links.unknownDevice')}
              </span>
              <span className="text-xs text-ink-muted">
                {t('management.links.lastSeen', {
                  when: formatSince(device.last_seen_at, t('common.never')),
                })}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}

function DictionariesCard() {
  const { t } = useTranslation();
  const dictionaries = useQuery(dictionariesQuery());

  return (
    <Card title={t('management.dictionaries.title')} question={t('management.dictionaries.body')}>
      {dictionaries.isPending ? <Loading /> : null}
      {dictionaries.isError ? <Failure detail={describeError(dictionaries.error)} /> : null}

      {dictionaries.data ? (
        <dl className="grid gap-3 sm:grid-cols-2">
          {DICTIONARY_TILES.map((tile) => {
            const entries: readonly DictionaryEntry[] = dictionaries.data[tile.field];
            return (
              // min-w-0 — по той же причине, что у карточки: элемент сетки шире своего
              // содержимого не бывает, а `truncate` внутри него без этого не работает.
              <div key={tile.field} className="min-w-0 rounded-[var(--radius)] bg-sunken px-3 py-2">
                <dt className="text-sm text-ink">{t(tile.label)}</dt>
                <dd className="mt-1 text-lg font-semibold text-ink-strong numeric">
                  {entries.length}
                </dd>
                <p className="mt-1 truncate text-xs text-ink-muted">
                  {entries
                    .slice(0, 3)
                    .map((entry) => entry.name.ru)
                    .join(', ')}
                </p>
              </div>
            );
          })}
        </dl>
      ) : null}
    </Card>
  );
}

function StateCard() {
  const { t } = useTranslation();
  const health = useHealth();

  return (
    <Card
      title={t('management.state.title')}
      question={t('management.state.body')}
      freshness={
        health.data
          ? t('management.state.answered', { when: formatSince(health.data.time, '') })
          : undefined
      }
    >
      {health.isPending ? <Loading /> : null}
      {health.isError ? <Failure detail={describeError(health.error)} /> : null}

      {health.data ? (
        <dl className="flex flex-col gap-2 text-sm">
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-ink-muted">{t('management.state.commit')}</dt>
            <dd className="truncate font-numeric text-ink-strong">{health.data.commit}</dd>
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-ink-muted">{t('management.state.env')}</dt>
            <dd className="text-ink-strong">
              {t(`management.state.envNames.${health.data.env}`, health.data.env)}
            </dd>
          </div>
        </dl>
      ) : null}
    </Card>
  );
}

export function ManagementSection() {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const canWrite = user.data?.can_write === true;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <span className="grid size-10 place-items-center rounded-[var(--radius)] bg-accent-soft text-accent-ink">
          <KeyRound className="size-5" />
        </span>
        <div>
          <h1 className="text-xl font-semibold text-ink-strong">{t('management.title')}</h1>
          <p className="text-sm text-ink-muted">{t('sectionQuestions.management')}</p>
        </div>
      </div>

      {user.data && !canWrite ? (
        <p className="text-sm text-ink-muted">{t('management.links.assistantOnly')}</p>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-2">
        {canWrite
          ? ROLES.map((role) => (
              <CardBoundary key={role} title={t(`role.${role}`)}>
                <LinkCard role={role} />
              </CardBoundary>
            ))
          : null}
        <CardBoundary title={t('management.dictionaries.title')}>
          <DictionariesCard />
        </CardBoundary>
        <CardBoundary title={t('management.state.title')}>
          <StateCard />
        </CardBoundary>
      </div>
    </div>
  );
}
