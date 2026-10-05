/**
 * Карточка письма (ТЗ 3.4): направление, организация, тема, номер и дата, срок ответа, наш
 * автор, связь, ответ — и два действия по ролям:
 *
 * - **руководитель оценивает полученный ответ** в одно касание: по существу, формально, не по
 *   сути (ТЗ 11, V38); повторное касание снимает оценку;
 * - **помощник отмечает ответ**: «Ответ получен» у исходящего, «Мы ответили» у входящего —
 *   дата и номер ответного письма.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { Role } from '@/shared/api/orbita';
import { formatDate } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Empty } from '@/shared/ui/States';

import { DirectionIcon, LetterBadge } from './LettersTab';
import { RATINGS, type InteractionView, type LetterRow } from './model';
import { letterNumber } from './text';
import { useAnswer, useRate } from './useInteraction';

const FIELD =
  'min-h-touch min-w-0 rounded-[var(--radius)] border border-line-strong bg-card px-2 text-sm text-ink';

export function LetterPanel({
  view,
  id,
  viewer,
  onOrganization,
}: {
  view: InteractionView;
  id: string;
  viewer: Role;
  onOrganization: (id: string) => void;
}) {
  const { t } = useTranslation();
  const letter = view.letters.find((each) => each.id === id);
  if (!letter) return <Empty label={t('interaction.letter.gone')} />;

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-col gap-2">
        <p className="flex flex-wrap items-center gap-2 text-sm text-ink-muted">
          <DirectionIcon direction={letter.direction} />
          <span>{t(`interaction.directions.${letter.direction}`)}</span>
          <button
            type="button"
            className="min-h-touch text-accent-ink underline-offset-2 hover:underline"
            onClick={() => onOrganization(letter.organization.id)}
          >
            {letter.organization.name}
          </button>
        </p>
        <h2 className="text-lg leading-snug font-semibold text-ink-strong">{letter.subject}</h2>
        <LetterBadge row={letter} />
      </header>

      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-2 text-sm">
        <dt className="text-ink-muted">{t('interaction.letter.numberTitle')}</dt>
        <dd className="numeric text-ink">{letterNumber(t, letter)}</dd>
        <dt className="text-ink-muted">{t('interaction.letter.due')}</dt>
        <dd className="numeric text-ink">
          {letter.due_on ? formatDate(letter.due_on) : t('interaction.letters.noDue')}
        </dd>
        <dt className="text-ink-muted">{t('interaction.letter.author')}</dt>
        <dd className="text-ink">{letter.author?.name ?? t('interaction.letter.noAuthor')}</dd>
        {letter.link ? (
          <>
            <dt className="text-ink-muted">{t('interaction.letter.link')}</dt>
            <dd className="text-ink">
              {t('interaction.letter.linkLine', {
                type: t(`interaction.links.${letter.link.type}`),
                title: letter.link.title,
              })}
            </dd>
          </>
        ) : null}
        <dt className="text-ink-muted">{t('interaction.letter.reply')}</dt>
        <dd className="numeric text-ink">
          {letter.reply
            ? [
                letter.reply.number
                  ? t('interaction.letter.replyLine', {
                      number: letter.reply.number,
                      date: formatDate(letter.reply.sent_on),
                    })
                  : t('interaction.letter.replyNoNumber', {
                      date: formatDate(letter.reply.sent_on),
                    }),
                t('interaction.letters.answeredIn', { days: letter.days }),
              ].join(' · ')
            : t('interaction.letter.noReply')}
        </dd>
      </dl>

      {letter.direction === 'outgoing' && letter.state === 'answered' ? (
        <Rating letter={letter} viewer={viewer} />
      ) : null}
      {letter.state !== 'answered' && viewer === 'assistant' ? (
        <AnswerForm key={letter.version} letter={letter} today={view.as_of.slice(0, 10)} />
      ) : null}
    </div>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-[var(--radius-lg)] border border-line bg-card p-4">
      <h3 className="mb-2 text-sm font-semibold text-ink-strong">{title}</h3>
      {children}
    </section>
  );
}

function Rating({ letter, viewer }: { letter: LetterRow; viewer: Role }) {
  const { t } = useTranslation();
  const rate = useRate();
  return (
    <Block title={t('interaction.letter.rate')}>
      {viewer === 'leader' ? (
        <div className="flex flex-wrap gap-2">
          {RATINGS.map((rating) => (
            <Button
              key={rating}
              size="small"
              look={letter.rating === rating ? 'primary' : 'plain'}
              aria-pressed={letter.rating === rating}
              disabled={rate.isPending}
              onClick={() =>
                rate.mutate({
                  id: letter.id,
                  rating: letter.rating === rating ? null : rating,
                  version: letter.version,
                })
              }
            >
              {t(`interaction.ratings.${rating}`)}
            </Button>
          ))}
        </div>
      ) : (
        <p className="text-sm text-ink">
          {letter.rating
            ? t(`interaction.ratings.${letter.rating}`)
            : t('interaction.letter.notRated')}
        </p>
      )}
      <p className="mt-2 text-xs text-ink-muted">{t('interaction.letter.rateHint')}</p>
    </Block>
  );
}

function AnswerForm({ letter, today }: { letter: LetterRow; today: string }) {
  const { t } = useTranslation();
  const answer = useAnswer();
  const [on, setOn] = useState(today);
  const [number, setNumber] = useState('');
  const title =
    letter.direction === 'outgoing'
      ? t('interaction.letter.markAnswered')
      : t('interaction.letter.markReplied');
  return (
    <Block title={title}>
      <form
        className="flex flex-col gap-2 sm:flex-row sm:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          answer.mutate({
            id: letter.id,
            on,
            number: number.trim() || null,
            version: letter.version,
          });
        }}
      >
        <label className="flex flex-col gap-1 text-xs text-ink-muted">
          {t('interaction.letter.answerDate')}
          <input
            type="date"
            className={FIELD}
            value={on}
            min={letter.sent_on}
            onChange={(event) => setOn(event.target.value || today)}
          />
        </label>
        <label className="flex flex-1 flex-col gap-1 text-xs text-ink-muted">
          {t('interaction.letter.answerNumber')}
          <input
            className={FIELD}
            value={number}
            onChange={(event) => setNumber(event.target.value)}
          />
        </label>
        <Button type="submit" look="primary" disabled={answer.isPending}>
          {title}
        </Button>
      </form>
    </Block>
  );
}
