/**
 * Календарь — договор данных раздела.
 *
 * Форма будущих ответов `GET /api/v1/calendar?from=…&to=…` и `GET /api/v1/cycles`. Экран
 * строится раньше API по правилу блока «экран → API» (CLAUDE.md): пока его не утвердили,
 * отвечает вымышленный сервер `demo.ts`, и замена его настоящим — замена тел функций в
 * `useCalendar.ts`.
 *
 * Календарь собирает даты всех разделов (CONTEXT: «все сроки, вехи, мероприятия и доклады
 * из всех разделов плюс годовые циклы»). В блоке 1 источников пять: сроки проектов, вехи,
 * задачи, годовые циклы, сроки исполнения решений руководителя. Поручения Ижро, письма,
 * соглашения, доклады и мероприятия приходят со своими разделами в блоке 2.
 *
 * **Числа считает сервер** (инвариант 2): ступени, горячие дни, их порог и окно, даты
 * циклов. Экран их только показывает.
 */

import type { Ref } from '@/sections/projects/model';
import type { DecisionKind, Step } from '@/sections/pult/model';

export type { Ref };

/** Откуда дата. Порядок — порядок показа в дне и в подписи горячего дня. */
export const KINDS = ['milestone', 'project', 'task', 'decision', 'cycle'] as const;

export type ItemKind = (typeof KINDS)[number];

/** Правило годового цикла (ТЗ 3.1, `backend/app/domain/cycles.py`). */
export type CycleRule = 'annual' | 'quarterly' | 'every_n_years';

/** Правило словами: «ежеквартально, 5-го числа». */
export interface CycleRuleFields {
  rule: CycleRule;
  /** Месяц срока; у ежеквартального — не спрашивается: кварталы календарные. */
  month: number;
  day: number;
  every_years: number;
  /** Год, от которого считается «раз в N лет»: без него неизвестно, какие именно годы. */
  anchor_year: number;
}

export interface CalendarItem {
  /** Идентификатор записи-источника; у даты цикла — `цикл:дата`, у цикла дат много. */
  id: string;
  kind: ItemKind;
  date: string;
  /** У решения без текста — `null`: подписью служит вид решения, как на Пульте. */
  title: string | null;
  decision_kind: DecisionKind | null;
  /** Чьё: проект или программа вехи, задачи, цикла; у срока проекта — `null`, он сам. */
  owner: { id: string; title: string } | null;
  /** Запись, которую открывает касание: проект, задача, решение или цикл. */
  target: { kind: 'project' | 'task' | 'decision' | 'cycle'; id: string };
  responsible: Ref | null;
  /** Ступень лестницы — та же, что на Пульте; у цикла и закрытого — `null` (допущение V16). */
  step: Step | null;
  deviation: number;
  /** Пройдена веха, готова задача, исполнено решение — зачёркнуто. */
  is_done: boolean;
  /**
   * Веха в день срока своего проекта: срок проекта не отдельной строкой, а здесь — одно
   * дело, один срок (допущение V15). Ступень — старшая из двух.
   */
  ends_project: boolean;
  /** Правило — у даты годового цикла. */
  cycle: CycleRuleFields | null;
}

/** Горячий день: незакрытых сроков не меньше порога (ТЗ 5; допущение V15). */
export interface HotDay {
  date: string;
  count: number;
  kinds: Partial<Record<ItemKind, number>>;
}

export interface CalendarView {
  as_of: string;
  /** Запрошенные дни включительно: месяц сеткой или две недели списком. */
  range: { from: string; to: string };
  /** Даты в запрошенных днях, по дню, внутри дня — ступень, затем вид. */
  items: CalendarItem[];
  /**
   * Незакрытое со сроком раньше сегодня — в каком бы месяце ни смотрели. Это «срок
   * прошёл», а не ступень Пульта «просрочено»: запись с вопросом руководителю здесь тоже,
   * а на Пульте она в «ждёт решения». Даты циклов сюда не входят: закрыть их нечем (V16).
   */
  overdue: CalendarItem[];
  /** Горячие дни в запрошенных днях — отметка на сетке и в списке. Прошедшие не горячие. */
  hot_days: HotDay[];
  /**
   * Ответ на «где неделя перегружена?»: горячие дни с сегодняшнего на `hot_window_days`
   * вперёд — в каком бы месяце ни смотрели.
   */
  hot_ahead: HotDay[];
  hot_window_days: number;
  hot_threshold: number;
  /** Сколько вперёд развёрнуты циклы и докуда листается календарь (`HORIZON_MONTHS`). */
  horizon_to: string;
  people: Ref[];
  /** Проекты в работе — для выбора в новом цикле. */
  projects: { id: string; title: string }[];
  is_demo: boolean;
}

/** Цикл в списке «Годовые циклы»: правило, чей и когда следующий раз. */
export interface CycleSummary extends CycleRuleFields {
  id: string;
  title: string;
  owner: { id: string; title: string } | null;
  responsible: Ref | null;
  /**
   * Ближайшая дата — и за горизонтом года: у цикла «раз в три года» дат на год вперёд
   * может не быть. `null` — дня нет ни в одном году (30 февраля).
   */
  next_date: string | null;
}

/** Цикл целиком — для листа по касанию: правило и даты на год вперёд. */
export interface CycleDetail extends CycleSummary {
  /** Даты на год вперёд — разворачивает сервер (`domain/cycles.occurrences`). */
  dates: string[];
  version: number;
}

/** Даты будущего цикла до записи. */
export interface CyclePreview {
  dates: string[];
  next_date: string | null;
}

/** Новый годовой цикл — вносит помощник. */
export interface NewCycle extends CycleRuleFields {
  title: string;
  project_id: string | null;
  responsible_id: string | null;
}
