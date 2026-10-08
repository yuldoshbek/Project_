/**
 * Данные повестки — те же запросы, что у экранов разделов, с теми же ключами кэша: открыли
 * раздел, вернулись — повестка не спрашивает сервер второй раз. Своего эндпоинта нет: экран
 * собирается из ответов, у которых уже есть место на экранах разделов.
 */

import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';

import { useCalendar } from '@/sections/calendar/useCalendar';
import { useIdeas } from '@/sections/ideas/useIdeas';
import { useIjro } from '@/sections/ijro/useIjro';
import { useInteraction } from '@/sections/interaction/useInteraction';
import { usePult } from '@/sections/pult/usePult';
import { useReports } from '@/sections/reports/useReports';
import { describeError } from '@/shared/api/client';
import { localDay } from '@/shared/time';

import {
  calendarSlide,
  failedSlide,
  ideasSlide,
  ijroSlide,
  interactionSlide,
  pultSlide,
  reportsSlide,
  type AgendaSection,
  type Slide,
} from './agenda';

interface Source<T> {
  data: T | undefined;
  isError: boolean;
  error: unknown;
}

/**
 * Слайд раздела: ответ, если данные есть (и тогда, когда фоновый опрос упал, — свежесть
 * скажет, на когда они), слайд «не удалось получить», если данных нет и запрос упал, и
 * ничего, пока запрос идёт.
 */
function slideOf<T>(
  t: TFunction,
  section: AgendaSection,
  source: Source<T>,
  build: (data: T) => Slide | null,
): Slide | null {
  if (source.data !== undefined) return build(source.data);
  if (source.isError) return failedSlide(t, section, describeError(source.error));
  return null;
}

export function useAgenda(): { slides: Slide[]; pending: boolean } {
  const { t } = useTranslation();
  const today = localDay(new Date());
  const pult = usePult();
  const ijro = useIjro();
  const reports = useReports();
  const interaction = useInteraction();
  const ideas = useIdeas();
  // Горячие дни отвечают за окно вперёд независимо от запрошенных дней: хватает одного дня.
  const calendar = useCalendar({ from: today, to: today });

  const slides = [
    slideOf(t, 'pult', pult, (data) => pultSlide(t, data)),
    slideOf(t, 'ijro', ijro, (data) => ijroSlide(t, data)),
    slideOf(t, 'reports', reports, (data) => reportsSlide(t, data)),
    slideOf(t, 'interaction', interaction, (data) => interactionSlide(t, data)),
    slideOf(t, 'ideas', ideas, (data) => ideasSlide(t, data)),
    slideOf(t, 'calendar', calendar, (data) => calendarSlide(t, data, today)),
  ].filter((each): each is Slide => each !== null);

  const pending = [pult, ijro, reports, interaction, ideas, calendar].some(
    (query) => query.isPending,
  );
  return { slides, pending };
}
