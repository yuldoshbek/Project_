/**
 * Значок типа записи — рядом со словом, а не вместо него: тип читается и без цвета.
 */

import { CalendarClock, CheckSquare, Lightbulb, Mail, MessageSquareQuote } from 'lucide-react';
import type { ComponentType } from 'react';

import type { CaptureKind } from './model';

export const KIND_ICON: Record<CaptureKind, ComponentType<{ className?: string }>> = {
  task: CheckSquare,
  request: MessageSquareQuote,
  idea: Lightbulb,
  letter: Mail,
  event: CalendarClock,
};
