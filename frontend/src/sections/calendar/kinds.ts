/**
 * Значок вида даты — слово дублируется значком, а не цветом: цвет в сетке занят ступенью.
 */

import { CheckSquare, Diamond, Flag, Gavel, Presentation, Repeat, ScrollText } from 'lucide-react';
import type { ComponentType } from 'react';

import type { ItemKind } from './model';

export const KIND_ICON: Record<ItemKind, ComponentType<{ className?: string }>> = {
  milestone: Diamond,
  project: Flag,
  task: CheckSquare,
  decision: Gavel,
  ijro: ScrollText,
  preparation: Presentation,
  cycle: Repeat,
};

/** Якорь дня в списке телефона — к нему прокручивает карточка горячих дней. */
export function dayAnchor(date: string): string {
  return `calendar-day-${date}`;
}
