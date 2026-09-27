/**
 * Программы — договор данных раздела.
 *
 * Форма будущего ответа `GET /api/v1/programs`. Экран строится раньше API по правилу блока
 * «экран → API» (CLAUDE.md): пока его не утвердили, отвечает вымышленный сервер `demo.ts`,
 * и замена его настоящим — замена тела одной функции в `usePrograms.ts`.
 *
 * Программа — многолетний проект (ТЗ 3.1, признак «многолетняя») со своими вехами и
 * подпроектами. Правят её в карточке проекта; раздел отвечает на свой вопрос: где мы по
 * программам и что должно случиться до конца года (ТЗ 2). Поэтому здесь нет ни форм, ни
 * версий записей — только чтение.
 *
 * **Числа считает сервер** (инвариант 2): дни до срока, ступени, готовность и отставание,
 * «успеваем?». Экран их только показывает.
 */

import type { ProjectStatus, Ref } from '@/sections/projects/model';
import type { Step } from '@/sections/pult/model';

export type { Ref };
export { TERMINAL } from '@/sections/projects/model';

export interface ProgramMilestone {
  id: string;
  title: string;
  due_on: string;
  /** Первое значение срока; перенос виден как «исходный → текущий» (ТЗ 11). */
  original_due_on: string;
  is_passed: boolean;
  passed_on: string | null;
  /** Календарных дней до срока по Ташкенту; минус — срок прошёл. */
  days_left: number;
  /** Ступень лестницы; `null` — по плану или пройдена. */
  step: Step | null;
  deviation: number;
}

export interface Subproject {
  id: string;
  code: string;
  title: string;
  status: ProjectStatus;
  responsible: Ref | null;
  started_on: string;
  due_on: string;
  original_due_on: string;
  readiness: number;
  step: Step | null;
  deviation: number;
  milestones: ProgramMilestone[];
}

/**
 * «Успеваем ли к дате программы?» (ТЗ 4, 5): ответ фразой с правилом.
 *
 * Темп — закрытые вехи и задачи программы и её подпроектов за последние `window_days`
 * дней. Прогноз — когда закроется оставшееся при этом темпе. Меньше `min_closed_tasks`
 * закрытых задач за то же время — «мало данных»: темп из трёх закрытых задач — шум, а не
 * прогноз (порог — справочник `min_closed_for_pace`).
 */
export type PaceVerdict = 'on_track' | 'behind' | 'little_data';

export interface Pace {
  verdict: PaceVerdict;
  window_days: number;
  /** Закрыто вех и задач за окно. */
  closed: number;
  /** Из них задач — по ним решается «мало данных» (ТЗ 4). */
  closed_tasks: number;
  min_closed_tasks: number;
  /** Осталось вех и задач. */
  remaining: number;
  /** Когда закроется оставшееся при этом темпе; `null` — мало данных или ничего не закрыто. */
  forecast_on: string | null;
  /** Прогноз минус дата программы, дни: плюс — не успеваем на столько, минус — запас. */
  gap_days: number | null;
}

export interface ProgramCard {
  id: string;
  code: string;
  title: string;
  type: { code: string; name: string };
  status: ProjectStatus;
  responsible: Ref | null;
  started_on: string;
  /** Дата программы — к ней идёт отсчёт. */
  due_on: string;
  original_due_on: string;
  /** Отсчёт: календарных дней до даты по Ташкенту; минус — дата прошла. */
  days_left: number;
  /**
   * Готовность, % — по закрытым вехам и задачам (ТЗ 3.1) программы **вместе с
   * подпроектами**; по тому же набору — отставание и «успеваем?» (допущение V13).
   */
  readiness: number;
  /** Отставание от плана, дни (ТЗ 4): плюс — отстаём, минус — идём с запасом. */
  lag_days: number;
  /** Ступень самой программы — по её сроку и признаку жизни, как у строки проекта. */
  step: Step | null;
  deviation: number;
  /** Свои вехи программы — по сроку. */
  milestones: ProgramMilestone[];
  subprojects: Subproject[];
  /** У завершённой и отменённой спрашивать «успеваем?» не о чем. */
  pace: Pace | null;
}

/** «Что должно случиться до конца года?» — веха с тем, чья она. */
export interface YearEndRow {
  milestone: ProgramMilestone;
  program: { id: string; code: string; title: string };
  /** Веха подпроекта; `null` — своя веха программы. */
  subproject: { id: string; title: string } | null;
  responsible: Ref | null;
}

export interface ProgramsView {
  as_of: string;
  /** Горизонт лет — пять лет от текущего (PLAN, блок 1: 2026–2030; допущение V14). */
  horizon: { from: number; to: number };
  /** Порядок — серверный: лестница внимания, затем по дате; закрытые в конце. */
  items: ProgramCard[];
  /**
   * Непройденные вехи программ и их подпроектов со сроком до 31 декабря: просроченные
   * первыми — они всё ещё должны случиться в этом году, — затем по сроку.
   */
  year_end: YearEndRow[];
  is_demo: boolean;
}
