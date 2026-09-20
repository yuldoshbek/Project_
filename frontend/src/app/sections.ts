/**
 * Десять разделов ТЗ — один список на всё приложение.
 *
 * Отсюда берутся и навигация на телефоне, и боковая полоса, и маршруты, и заголовки. Один
 * список, потому что три копии расходятся: раздел добавили в меню, забыли в маршрутах, и
 * ссылка ведёт на пустой экран.
 *
 * У каждого раздела записан **вопрос**, на который он отвечает, и блок, в котором он
 * появляется (docs/PLAN.md). Вопрос виден на экране заглушки: так заказчик на приёмке
 * блока 0 видит не «скоро будет», а что именно здесь будет и зачем.
 */

import {
  Calendar,
  ClipboardList,
  FileText,
  Gauge,
  Layers,
  Lightbulb,
  ListChecks,
  Presentation,
  Settings,
  Users,
} from 'lucide-react';
import type { ComponentType } from 'react';

export interface SectionDefinition {
  /** Часть пути и ключ перевода. */
  id: string;
  icon: ComponentType<{ className?: string }>;
  /** В каком блоке раздел наполняется данными (docs/PLAN.md); 0 — работает уже сейчас. */
  block: 0 | 1 | 2 | 3;
  /** Показывать ли в нижней панели телефона: там пять мест, не больше. */
  onPhone: boolean;
}

export const SECTIONS: readonly SectionDefinition[] = [
  { id: 'pult', icon: Gauge, block: 1, onPhone: true },
  { id: 'programs', icon: Layers, block: 1, onPhone: false },
  { id: 'projects', icon: ClipboardList, block: 1, onPhone: true },
  { id: 'tasks', icon: ListChecks, block: 1, onPhone: true },
  { id: 'ijro', icon: FileText, block: 2, onPhone: true },
  { id: 'interaction', icon: Users, block: 2, onPhone: false },
  { id: 'reports', icon: Presentation, block: 2, onPhone: false },
  { id: 'ideas', icon: Lightbulb, block: 3, onPhone: false },
  { id: 'calendar', icon: Calendar, block: 1, onPhone: false },
  { id: 'management', icon: Settings, block: 0, onPhone: true },
];

/**
 * Разделы для нижней панели телефона: пять и ни одного больше.
 *
 * Шестая кнопка в панели шириной 390 px делает цель нажатия меньше 44 px — то есть
 * промахи там, где руководитель принимает решения одной рукой.
 */
export const PHONE_SECTIONS = SECTIONS.filter((section) => section.onPhone);

export function sectionPath(id: string): string {
  return id === 'pult' ? '/' : `/${id}`;
}
