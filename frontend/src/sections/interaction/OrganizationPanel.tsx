/**
 * Карточка организации — собирает письма, поручения, проекты и соглашения (ТЗ 11).
 *
 * Скорость ответа — медиана при пяти письмах с ответом и больше; меньше — сколько есть и
 * сколько нужно, словами (ТЗ 4). Оценки ответов — сколько каких поставил руководитель.
 */

import { useTranslation } from 'react-i18next';

import { STEP_SIGNAL } from '@/sections/pult/model';
import { describeError } from '@/shared/api/client';
import { Failure, Loading } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';

import { LetterBadge } from './LettersTab';
import { RATINGS, type OrganizationCard } from './model';
import { agreementStatus, speedText } from './text';
import { useInteraction, useOrganization } from './useInteraction';

export function OrganizationPanel({
  id,
  onLetter,
}: {
  id: string;
  onLetter: (id: string) => void;
}) {
  const card = useOrganization(id);
  if (card.isPending) return <Loading />;
  if (card.isError) return <Failure detail={describeError(card.error)} />;
  return <Panel card={card.data} onLetter={onLetter} />;
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-[var(--radius-lg)] border border-line bg-card p-4">
      <h3 className="mb-2 text-sm font-semibold text-ink-strong">{title}</h3>
      {children}
    </section>
  );
}

function Panel({ card, onLetter }: { card: OrganizationCard; onLetter: (id: string) => void }) {
  const { t } = useTranslation();
  const view = useInteraction();
  const min = view.data?.thresholds.min_letters ?? 5;
  const none = <p className="text-sm text-ink-muted">{t('interaction.organization.none')}</p>;
  const rated = RATINGS.filter((rating) => card.ratings[rating] > 0);

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-col gap-1">
        <h2 className="text-lg leading-snug font-semibold text-ink-strong">{card.name}</h2>
        <p className="text-sm text-ink-muted">
          {[
            card.short_name,
            card.is_founded_by_agency
              ? t('interaction.organizations.center')
              : t(`interaction.kinds.${card.kind}`),
          ]
            .filter(Boolean)
            .join(' · ')}
        </p>
        {card.phone || card.email ? (
          <p className="numeric text-sm text-ink">
            {[card.phone, card.email].filter(Boolean).join(' · ')}
          </p>
        ) : null}
      </header>

      <Block title={t('interaction.organization.speed')}>
        <p className="text-sm text-ink">
          {card.speed.median_days !== null
            ? t('interaction.organization.speedLine', {
                days: card.speed.median_days,
                count: card.speed.letters,
              })
            : card.speed.letters > 0
              ? t('interaction.organization.speedLittle', { count: card.speed.letters, min })
              : speedText(t, card)}
        </p>
        {rated.length > 0 ? (
          <p className="mt-2 text-xs text-ink-muted">
            {t('interaction.organization.ratings')}{' '}
            {rated
              .map((rating) => `${t(`interaction.ratings.${rating}`)} ${card.ratings[rating]}`)
              .join(' · ')}
          </p>
        ) : null}
      </Block>

      <Block title={t('interaction.organization.letters')}>
        {card.letters.length === 0 ? (
          none
        ) : (
          <ul className="divide-y divide-line">
            {card.letters.map((letter) => (
              <li key={letter.id}>
                <button
                  type="button"
                  className="flex min-h-touch w-full flex-col gap-1 py-2 text-left"
                  onClick={() => onLetter(letter.id)}
                >
                  <LetterBadge row={letter} />
                  <span className="text-sm text-ink-strong">{letter.subject}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Block>

      <Block title={t('interaction.organization.agreements')}>
        {card.agreements.length === 0 ? (
          none
        ) : (
          <ul className="flex flex-col gap-2 text-sm">
            {card.agreements.map((agreement) => (
              <li key={agreement.id}>
                <span className="text-ink-strong">{agreement.title}</span>
                <span className="mt-1 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
                  {agreement.step ? (
                    <Signal state={agreement.sleeping ? 'wait' : STEP_SIGNAL[agreement.step]}>
                      {agreement.sleeping
                        ? t('interaction.agreements.sleeping')
                        : t(`pult.steps.${agreement.step}`)}
                    </Signal>
                  ) : null}
                  <span className="numeric">{agreementStatus(t, agreement)}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Block>

      <Block title={t('interaction.organization.ijro')}>
        {card.ijro.length === 0 ? (
          none
        ) : (
          <ul className="flex flex-col gap-2 text-sm">
            {card.ijro.map((each) => (
              <li key={each.id}>
                <span className="numeric flex flex-wrap items-center gap-2 text-xs text-ink-muted">
                  {each.step ? (
                    <Signal state={STEP_SIGNAL[each.step]}>{t(`pult.steps.${each.step}`)}</Signal>
                  ) : null}
                  {each.place}
                </span>
                <span className="mt-1 block text-ink">{each.content}</span>
              </li>
            ))}
          </ul>
        )}
      </Block>

      <Block title={t('interaction.organization.projects')}>
        {card.projects.length === 0 ? (
          none
        ) : (
          <ul className="flex flex-col gap-1 text-sm">
            {card.projects.map((each) => (
              <li key={each.id} className="flex flex-wrap gap-x-2">
                <span className="numeric text-ink-muted">{each.code}</span>
                <span className="text-ink-strong">{each.title}</span>
                <span className="text-ink-muted">· {t(`projects.roles.${each.role}`)}</span>
              </li>
            ))}
          </ul>
        )}
      </Block>
    </div>
  );
}
