/**
 * Данные повестки — те же запросы, что у экранов разделов, с теми же ключами кэша: открыли
 * раздел, вернулись — повестка не спрашивает сервер второй раз. Своего эндпоинта нет: экран
 * собирается из ответов, у которых уже есть место на экранах разделов.
 */

import { useTranslation } from 'react-i18next';

import { useCalendar } from '@/sections/calendar/useCalendar';
import { useIdeas } from '@/sections/ideas/useIdeas';
import { useIjro } from '@/sections/ijro/useIjro';
import { useInteraction } from '@/sections/interaction/useInteraction';
import { usePult } from '@/sections/pult/usePult';
import { useReports } from '@/sections/reports/useReports';
import { localDay } from '@/shared/time';

import {
  calendarSlide,
  ideasSlide,
  ijroSlide,
  interactionSlide,
  pultSlide,
  reportsSlide,
  type Slide,
} from './agenda';

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
    pult.data ? pultSlide(t, pult.data) : null,
    ijro.data ? ijroSlide(t, ijro.data) : null,
    reports.data ? reportsSlide(t, reports.data) : null,
    interaction.data ? interactionSlide(t, interaction.data) : null,
    ideas.data ? ideasSlide(t, ideas.data) : null,
    calendar.data ? calendarSlide(t, calendar.data, today) : null,
  ].filter((each): each is Slide => each !== null);

  const pending = [pult, ijro, reports, interaction, ideas, calendar].some(
    (query) => query.isPending,
  );
  return { slides, pending };
}
