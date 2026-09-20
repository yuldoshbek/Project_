/**
 * Управление — единственный раздел, который работает с настоящими данными в блоке 0.
 *
 * Три карточки, каждая отвечает на свой вопрос:
 *
 * - **Ссылки доступа** — «кто может войти и как закрыть доступ». Здесь же видно устройства:
 *   лишняя строка означает чужой вход.
 * - **Справочники** — «наполнена ли система». Это критерий приёмки блока: в рабочей базе
 *   справочники заведены, в демо — вымышленные данные.
 * - **Состояние** — «что именно выложено». Коммит из `/api/health` отвечает на вопрос,
 *   который иначе выясняется по поведению системы.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy, KeyRound, RefreshCw } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { ApiError } from '@/shared/api/client';
import { api, type AccessLink, type Role } from '@/shared/api/orbita';
import { formatDateTime, formatSince } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';
import { Empty, Failure, Loading } from '@/shared/ui/States';

const ROLES: readonly Role[] = ['assistant', 'leader'];

function detailOf(error: unknown): string {
  return error instanceof ApiError ? error.detail : String(error);
}

function LinkCard({ role }: { role: Role }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [issued, setIssued] = useState<AccessLink | null>(null);
  const [copied, setCopied] = useState(false);

  const sessions = useQuery({
    queryKey: ['sessions', role],
    queryFn: () => api.sessions(role),
    retry: (attempt, error) => !(error instanceof ApiError && error.readOnly) && attempt < 2,
  });

  const reissue = useMutation({
    mutationFn: () => api.reissueLink(role),
    onSuccess: async (link) => {
      setIssued(link);
      setCopied(false);
      // Сессии гаснут вместе с перевыпуском — список устройств обязан это показать сразу,
      // иначе кнопка выглядит не сработавшей.
      await client.invalidateQueries({ queryKey: ['sessions', role] });
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
      {reissue.isError ? <Failure detail={detailOf(reissue.error)} /> : null}

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
      {sessions.isError ? <Failure detail={detailOf(sessions.error)} /> : null}
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
  const dictionaries = useQuery({ queryKey: ['dictionaries'], queryFn: api.dictionaries });

  const groups = [
    { key: 'directions', label: t('management.dictionaries.directions') },
    { key: 'projectStatuses', label: t('management.dictionaries.projectStatuses') },
    { key: 'taskStatuses', label: t('management.dictionaries.taskStatuses') },
    { key: 'priorities', label: t('management.dictionaries.priorities') },
  ] as const;

  const counts = dictionaries.data
    ? {
        directions: dictionaries.data.directions,
        projectStatuses: dictionaries.data.project_statuses,
        taskStatuses: dictionaries.data.task_statuses,
        priorities: dictionaries.data.priorities,
      }
    : null;

  return (
    <Card title={t('management.dictionaries.title')} question={t('management.dictionaries.body')}>
      {dictionaries.isPending ? <Loading /> : null}
      {dictionaries.isError ? <Failure detail={detailOf(dictionaries.error)} /> : null}

      {counts ? (
        <dl className="grid gap-3 sm:grid-cols-2">
          {groups.map((group) => (
            // min-w-0 — по той же причине, что у карточки: элемент сетки шире своего
            // содержимого не бывает, а `truncate` внутри него без этого не работает.
            <div key={group.key} className="min-w-0 rounded-[var(--radius)] bg-sunken px-3 py-2">
              <dt className="text-sm text-ink">{group.label}</dt>
              <dd className="mt-1 text-lg font-semibold text-ink-strong numeric">
                {counts[group.key].length}
              </dd>
              <p className="mt-1 truncate text-xs text-ink-muted">
                {counts[group.key]
                  .slice(0, 3)
                  .map((entry) => entry.name.ru)
                  .join(', ')}
              </p>
            </div>
          ))}
        </dl>
      ) : null}
    </Card>
  );
}

function StateCard() {
  const { t } = useTranslation();
  const health = useQuery({ queryKey: ['health'], queryFn: api.health });

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
      {health.isError ? <Failure detail={detailOf(health.error)} /> : null}

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

      <div className="grid gap-4 xl:grid-cols-2">
        {ROLES.map((role) => (
          <LinkCard key={role} role={role} />
        ))}
        <DictionariesCard />
        <StateCard />
      </div>
    </div>
  );
}
