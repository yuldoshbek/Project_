/**
 * Доступ — «кто может войти и как закрыть доступ» (ТЗ 3.8, ADR-0029).
 *
 * Устройства и перевыпуск — настоящий API блока 0: кнопка гасит прежние сессии сразу, и
 * лишняя строка в устройствах означает чужой вход. Дата выпуска и последний вход пока с
 * вымышленного сервера — API раздела отдаст их вместе с устройствами; настоящий перевыпуск
 * вымышленный сервер запоминает. Последний вход не пропадает вместе с сессиями: после
 * перевыпуска или истечения их нет, а вопрос «когда он заходил» остаётся. Перевыпуск
 * переспрашивает: одно случайное касание выкидывает из системы и того, кто нажал.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy, RefreshCw } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { Device } from '@/app/device';
import { useHealth } from '@/app/session';
import { describeError } from '@/shared/api/client';
import { api, type AccessLink, type Role } from '@/shared/api/orbita';
import { sessionsQuery } from '@/shared/api/queries';
import { cn } from '@/shared/lib/cn';
import { formatDateTime, formatSince } from '@/shared/time';
import { CardBoundary } from '@/shared/ui/Boundary';
import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';
import { Empty, Failure, Loading } from '@/shared/ui/States';

import type { ManagementView } from './model';
import { useLinkIssued } from './useManagement';

function LinkCard({
  role,
  issuedAt,
  lastLoginAt,
}: {
  role: Role;
  issuedAt: string | null;
  lastLoginAt: string | null;
}) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [asking, setAsking] = useState(false);
  const [issued, setIssued] = useState<AccessLink | null>(null);
  const [copied, setCopied] = useState(false);

  const sessions = useQuery(sessionsQuery(role));
  const linkIssued = useLinkIssued();

  const reissue = useMutation({
    mutationFn: () => api.reissueLink(role),
    onSuccess: async (link) => {
      setIssued(link);
      setCopied(false);
      setAsking(false);
      linkIssued(role, link.issued_at);
      // Сессии гаснут вместе с перевыпуском — список устройств обязан это показать сразу,
      // иначе кнопка выглядит не сработавшей.
      await client.invalidateQueries({ queryKey: sessionsQuery(role).queryKey });
    },
  });

  const current = issued?.issued_at ?? issuedAt;
  // Самое свежее из записанного входа и движения открытых сессий.
  const seen = [lastLoginAt, ...(sessions.data ?? []).map((device) => device.last_seen_at)]
    .filter((when): when is string => when !== null)
    .sort((a, b) => Date.parse(a) - Date.parse(b))
    .at(-1);

  return (
    <Card
      title={t(`role.${role}`)}
      question={t('management.links.body')}
      action={
        <Button look="primary" size="small" onClick={() => setAsking(true)} disabled={asking}>
          <RefreshCw className="size-4" aria-hidden="true" />
          {t('management.links.reissue')}
        </Button>
      }
    >
      <p className="numeric mb-3 text-sm text-ink">
        {[
          current ? t('management.links.current', { when: formatDateTime(current) }) : null,
          t('management.links.lastLogin', { when: formatSince(seen ?? null, t('common.never')) }),
        ]
          .filter(Boolean)
          .join(' · ')}
      </p>

      {asking ? (
        <div className="mb-4 flex flex-col gap-2 rounded-[var(--radius)] border border-line-strong bg-sunken p-3">
          <p className="text-sm text-ink">{t('management.links.confirm')}</p>
          <span className="flex flex-wrap gap-2">
            <Button
              look="primary"
              size="small"
              onClick={() => reissue.mutate()}
              disabled={reissue.isPending}
            >
              {t('management.links.confirmYes')}
            </Button>
            <Button
              size="small"
              onClick={() => {
                setAsking(false);
                reissue.reset();
              }}
            >
              {t('management.links.confirmNo')}
            </Button>
          </span>
        </div>
      ) : null}

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
              <Copy className="size-4" aria-hidden="true" />
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
            <dd className="numeric truncate text-ink-strong">{health.data.commit}</dd>
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

const ROLES: readonly Role[] = ['assistant', 'leader'];

const COLUMNS: Record<Device, string> = {
  phone: 'grid-cols-1',
  laptop: 'grid-cols-2',
  monitor: 'grid-cols-3',
};

export function AccessTab({ links, device }: { links: ManagementView['links']; device: Device }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-4">
      <div className={cn('grid items-start gap-4', COLUMNS[device])}>
        {ROLES.map((role) => (
          <CardBoundary key={role} title={t(`role.${role}`)}>
            <LinkCard
              role={role}
              issuedAt={links.find((each) => each.role === role)?.issued_at ?? null}
              lastLoginAt={links.find((each) => each.role === role)?.last_login_at ?? null}
            />
          </CardBoundary>
        ))}
        <CardBoundary title={t('management.state.title')}>
          <StateCard />
        </CardBoundary>
      </div>
      <p className="text-sm text-ink-muted">{t('management.links.real')}</p>
      <p className="text-sm text-ink-muted">{t('management.upload')}</p>
    </div>
  );
}
