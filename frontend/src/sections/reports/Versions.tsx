/**
 * Версии презентации доклада (ТЗ 3.5): загрузка файла, просмотр PDF, статус, замечания на
 * слайд.
 *
 * Загружает версию помощник; статус ставят оба — руководитель чаще («на доработке»,
 * «принята»); замечание на слайд пишут оба; «исправлено» отмечает помощник, и замечание
 * запоминает, в какой версии его исправили. PDF открывается в браузере по короткоживущей
 * ссылке — его предпросмотр и есть встроенный просмотрщик браузера (раздел «Файлы»).
 */

import { ExternalLink, Upload } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { describeError } from '@/shared/api/client';
import type { Role } from '@/shared/api/orbita';
import { cn } from '@/shared/lib/cn';
import { formatDateTime } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Signal } from '@/shared/ui/Signal';

import { VERSION_STATES, type PreparationCard, type PresentationVersion } from './model';
import {
  fileLink,
  useAddComment,
  useFixComment,
  useUploadVersion,
  useVersionState,
} from './useReports';

const FIELD =
  'min-h-touch min-w-0 rounded-[var(--radius)] border border-line-strong bg-card px-2 text-sm text-ink';

const STATE_SIGNAL = { review: 'plain', rework: 'wait', accepted: 'calm' } as const;

export function Versions({ card, viewer }: { card: PreparationCard; viewer: Role }) {
  const { t } = useTranslation();
  const upload = useUploadVersion();
  const latest = card.versions[0];

  return (
    <section className="rounded-[var(--radius-lg)] border border-line bg-card p-4">
      <header className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-ink-strong">{t('reports.versions.title')}</h3>
        {viewer === 'assistant' ? (
          <label
            className={cn(
              'inline-flex min-h-touch cursor-pointer items-center gap-2 rounded-[var(--radius)] border border-line-strong px-3 text-sm font-medium text-ink',
              upload.isPending && 'pointer-events-none opacity-60',
            )}
          >
            <Upload className="size-4" aria-hidden="true" />
            {upload.isPending ? t('reports.versions.uploading') : t('reports.versions.upload')}
            <input
              type="file"
              accept=".pdf,.pptx,.ppt"
              className="sr-only"
              aria-label={t('reports.versions.upload')}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) upload.mutate({ id: card.id, file });
                event.target.value = '';
              }}
            />
          </label>
        ) : null}
      </header>
      {upload.isError ? (
        <p role="alert" className="mb-2 text-sm text-burn-ink">
          {describeError(upload.error)}
        </p>
      ) : null}
      {card.versions.length === 0 ? (
        <p className="text-sm text-ink-muted">{t('reports.versions.none')}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {card.versions.map((version) => (
            <VersionLine
              key={version.id}
              card={card}
              version={version}
              viewer={viewer}
              isLatest={version.id === latest?.id}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function VersionLine({
  card,
  version,
  viewer,
  isLatest,
}: {
  card: PreparationCard;
  version: PresentationVersion;
  viewer: Role;
  isLatest: boolean;
}) {
  const { t } = useTranslation();
  const setState = useVersionState();
  const fix = useFixComment();
  const add = useAddComment();
  const [slide, setSlide] = useState('');
  const [text, setText] = useState('');
  const [opening, setOpening] = useState(false);
  const open = async () => {
    setOpening(true);
    try {
      window.open(await fileLink(version.file.id), '_blank', 'noopener');
    } finally {
      setOpening(false);
    }
  };

  return (
    <li className="rounded-[var(--radius)] border border-line p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold text-ink-strong">
          {t('reports.versions.number', { number: version.number })}
        </span>
        <Signal state={STATE_SIGNAL[version.state]}>
          {t(`reports.versions.states.${version.state}`)}
        </Signal>
        <span className="numeric text-xs text-ink-muted">
          {formatDateTime(version.uploaded_at)}
        </span>
        <Button size="small" look="quiet" disabled={opening} onClick={() => void open()}>
          <ExternalLink className="size-4" aria-hidden="true" />
          {t('reports.versions.open')}
        </Button>
      </div>
      <p className="mt-1 truncate text-xs text-ink-muted">{version.file.name}</p>
      {/* Решают по последней версии; у прежних статус уже итог, кнопки только шумят. */}
      <div className={cn('mt-2 flex flex-wrap gap-2', !isLatest && 'hidden')}>
        {VERSION_STATES.map((state) => (
          <Button
            key={state}
            size="small"
            look={version.state === state ? 'primary' : 'plain'}
            aria-pressed={version.state === state}
            disabled={setState.isPending}
            onClick={() =>
              setState.mutate({
                id: card.id,
                versionId: version.id,
                state,
                version: version.version,
              })
            }
          >
            {t(`reports.versions.states.${state}`)}
          </Button>
        ))}
      </div>
      {version.comments.length > 0 ? (
        <ul className="mt-3 flex flex-col gap-2">
          {version.comments.map((comment) => (
            <li key={comment.id} className="text-sm">
              <span className="numeric font-medium text-ink-strong">
                {t('reports.versions.slide', { slide: comment.slide })}
              </span>{' '}
              <span className={cn(comment.fixed_in ? 'text-ink-muted line-through' : 'text-ink')}>
                {comment.text}
              </span>
              <span className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
                {comment.author ? t(`role.${comment.author}`) : null}
                {comment.fixed_in ? (
                  <Signal state="calm">
                    {t('reports.versions.fixedIn', { number: comment.fixed_in })}
                  </Signal>
                ) : null}
                {viewer === 'assistant' ? (
                  <Button
                    size="small"
                    look="quiet"
                    disabled={fix.isPending}
                    onClick={() =>
                      fix.mutate({
                        id: card.id,
                        commentId: comment.id,
                        fixed: comment.fixed_in === null,
                        version: comment.version,
                      })
                    }
                  >
                    {comment.fixed_in ? t('reports.versions.unfix') : t('reports.versions.fix')}
                  </Button>
                ) : null}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {isLatest ? (
        <form
          className="mt-3 grid gap-2 sm:grid-cols-[6rem_1fr_auto]"
          onSubmit={(event) => {
            event.preventDefault();
            const number = Number(slide);
            if (!number || !text.trim()) return;
            add.mutate(
              { id: card.id, versionId: version.id, slide: number, text },
              {
                onSuccess: () => {
                  setSlide('');
                  setText('');
                },
              },
            );
          }}
        >
          <input
            type="number"
            min={1}
            inputMode="numeric"
            aria-label={t('reports.versions.slideLabel')}
            placeholder={t('reports.versions.slideLabel')}
            className={FIELD}
            value={slide}
            onChange={(event) => setSlide(event.target.value)}
          />
          <input
            aria-label={t('reports.versions.commentLabel')}
            placeholder={t('reports.versions.commentLabel')}
            className={FIELD}
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <Button type="submit" disabled={add.isPending || !slide || !text.trim()}>
            {t('reports.versions.comment')}
          </Button>
        </form>
      ) : null}
    </li>
  );
}
