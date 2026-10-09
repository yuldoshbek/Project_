/**
 * Многопанельный обзор на мониторе (ТЗ 6): главный вопрос каждого раздела рядом с Пультом.
 *
 * Пульт отвечает за лестницу; панели — за то, чего в лестнице нет: «готовы ли к дате»,
 * «кто не отвечает», «что ждёт моего „да“», «где неделя перегружена». Касание ведёт в
 * раздел — там действие. У Календаря — полоса на четыре недели: касание дня открывает его.
 * Подробность — не длиннее трёх строк: одна длинная панель растягивала все пять по высоте,
 * и в остальных под ответом стояла пустота (снимки блока 3).
 */

import { useNavigate } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';

import { HotStrip } from '@/sections/calendar/HotStrip';
import { cn } from '@/shared/lib/cn';
import { Card } from '@/shared/ui/Card';

import { useAgenda } from './useAgenda';

export default function Overview() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { slides } = useAgenda();
  const panels = slides.filter((slide) => slide.section !== 'pult');
  if (panels.length === 0) return null;
  return (
    <section aria-label={t('meeting.overview')} className="grid grid-cols-5 gap-6">
      {panels.map((slide) => (
        <Card
          key={slide.key}
          title={slide.question}
          freshness={slide.freshness ?? undefined}
          className="flex flex-col"
        >
          <p className="text-xs text-ink-muted">{t(`sections.${slide.section}`)}</p>
          <p
            className={cn(
              'mt-1 text-lg leading-snug font-semibold',
              slide.failed ? 'text-burn-ink' : slide.empty ? 'text-calm-ink' : 'text-ink-strong',
            )}
          >
            {slide.main}
          </p>
          {slide.detail ? (
            <p className="mt-1 line-clamp-3 text-sm text-ink-muted">{slide.detail}</p>
          ) : null}
          {slide.strip ? (
            <HotStrip
              today={slide.strip.today}
              hot={slide.strip.hot}
              onPick={(day) => void navigate({ to: '/calendar', search: { day } })}
            />
          ) : null}
          <div className="mt-auto pt-3">
            <button
              type="button"
              onClick={() => void navigate({ to: slide.path })}
              className="min-h-touch rounded-[var(--radius)] text-sm font-medium text-accent-ink hover:underline md:min-h-9"
            >
              {t('meeting.openSection', { section: t(`sections.${slide.section}`) })}
            </button>
          </div>
        </Card>
      ))}
    </section>
  );
}
