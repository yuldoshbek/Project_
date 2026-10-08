/**
 * Управление — договор данных `GET /api/v1/management` и правок раздела.
 *
 * Экран утверждён заказчиком 29.09.2026 на вымышленных данных той же формы; API написан под
 * него (CLAUDE.md, цикл блока «экран → API»). Устройства и перевыпуск ссылок — API блока 0
 * (`/api/access/…`).
 *
 * Управление — раздел помощника (CONTEXT, ТЗ 1.2): справочники, пороги, ссылки доступа,
 * обход (критерий ТЗ 11). Загрузка таблиц Ижро приходит с разделом Ижро в блоке 2.
 */

import type { Role } from '@/shared/api/orbita';

export const TABS = ['round', 'dictionaries', 'thresholds', 'access'] as const;

export type Tab = (typeof TABS)[number];

/** Почему пункт стоит в обходе — «почему вы здесь» (ТЗ 7). */
export type RoundReason =
  /** Срок исполнения решения руководителя прошёл, а оно открыто. */
  | 'decision_overdue'
  /** Задача просрочена: сделана, но не отмечена, или срок пора честно перенести. */
  | 'task_overdue'
  /** Срок вехи прошёл, а она не отмечена пройденной. */
  | 'milestone_passed'
  /** Задача на проверке дольше порога молчания. */
  | 'task_review'
  /** «Что мешает» записано давно — мешает ли ещё. */
  | 'impediment_stale'
  /** Проект молчит дольше порога: ни правки, ни движения задач и вех. */
  | 'project_silent'
  /** Открытая задача без ответственного. */
  | 'task_unassigned';

/**
 * Действие в одно касание. Каждое меняет данные: кнопки «всё нормально» нет (ТЗ 7) —
 * пункт уходит из обхода, когда данные догнали жизнь, а не когда его отметили.
 */
export type RoundAction =
  | 'decision_done'
  | 'task_done'
  | 'task_cancel'
  | 'task_back'
  | 'move_week'
  | 'milestone_passed'
  | 'impediment_confirm'
  | 'impediment_clear'
  /** Записать «что мешает» — одной строкой прямо в обходе. */
  | 'note'
  /** Поставить проект на паузу — причина обязательна (статус «на паузе»). */
  | 'hold'
  /** Проект сделан, а его не закрыли: статус «завершён», причина не нужна. */
  | 'project_done'
  /** Назначить ответственного из списка. */
  | 'assign';

/** Действия, которым нужна строка или выбор, прежде чем записать. */
export const NEEDS_INPUT: ReadonlySet<RoundAction> = new Set(['note', 'hold', 'assign']);

export interface RoundItem {
  id: string;
  reason: RoundReason;
  /** Что открывается касанием названия. */
  target: { kind: 'project' | 'task'; id: string };
  /**
   * Запись, которую меняет действие, и её версия (инвариант 15): у вехи — веха, хотя
   * касание названия открывает её проект; у решения — решение.
   */
  record: { kind: 'decision' | 'task' | 'milestone' | 'project'; id: string; version: number };
  title: string;
  /** К чему относится: номер и название проекта; у задачи без проекта — null. */
  owner: string | null;
  responsible: string | null;
  /** Сколько дней: просрочки, молчания, давности — у каждой причины своё. */
  days: number;
  /** Два-три действия, в порядке кнопок. */
  actions: RoundAction[];
}

export interface Round {
  /** Неделя обхода — с понедельника по воскресенье. */
  week_from: string;
  week_to: string;
  items: RoundItem[];
  /** Пройдено на этой неделе действиями обхода. */
  done: number;
}

export type ThresholdKey =
  | 'burn_days'
  | 'quiet_days'
  | 'impediment_stale_days'
  | 'min_closed_for_pace'
  | 'hot_day_threshold'
  | 'hot_window_days'
  | 'summary_at'
  | 'sleeping_days'
  | 'min_letters_for_speed';

export interface Threshold {
  key: ThresholdKey;
  /** Дни и счёт — числом, время сводки — «08:30». */
  value: number | string;
  /** Значение по умолчанию: к нему возвращаются одним касанием. */
  default: number | string;
  /** Откуда значение по умолчанию: названо в ТЗ или принято допущением (V15 и др.). */
  origin: 'tz' | 'assumption';
  kind: 'days' | 'count' | 'time';
  /**
   * Границы: порог «горит за 900 дней» выключает сигнал, ни о чём не сказав. У времени сводки —
   * «ЧЧ:ММ»: окно, в котором сводку ещё успевает отправить расписание.
   */
  min: number | string | null;
  max: number | string | null;
  /** Сколько строк этот порог делает сигналом сейчас; у времени сводки — null. */
  affected: number | null;
  version: number;
}

export type DictionaryKind =
  | 'project_types'
  | 'task_types'
  | 'directions'
  | 'regions'
  | 'project_statuses'
  | 'task_statuses'
  | 'organizations';

export type OrganizationKind = 'ministry' | 'agency' | 'khokimiyat' | 'international' | 'company';

export interface DictionaryEntry {
  id: string;
  name: string;
  is_active: boolean;
  /** Сколько записей ссылается на значение: у выключенного они остаются своими. */
  used: number;
  version: number;
  /** Только у организаций: вид и признак учреждённой агентством (Центр). */
  org_kind?: OrganizationKind;
  is_center?: boolean;
}

export interface DictionaryGroup {
  kind: DictionaryKind;
  /** В порядке, в котором значения стоят в формах. */
  entries: DictionaryEntry[];
  /** Добавлять значения можно не везде: статусы заданы правилами переходов, регионы — ТЗ. */
  can_add: boolean;
  /** Выключить статус нельзя: на нём граф переходов. */
  can_disable: boolean;
  /** Организации идут по названию — «выше» и «ниже» у них нет. */
  can_move: boolean;
}

export interface TemplateStep {
  id: string;
  name: string;
  /** Через сколько дней от начала проекта — срок вехи в новом проекте. */
  offset_days: number;
  version: number;
}

export interface Person {
  id: string;
  name: string;
}

export interface ManagementView {
  as_of: string;
  round: Round;
  thresholds: Threshold[];
  dictionaries: DictionaryGroup[];
  /** Шаблоны вех по идентификатору типа проекта (ТЗ 3.9: «типы проектов с шаблонами вех»). */
  templates: Record<string, TemplateStep[]>;
  /** Кого можно назначить из обхода. */
  people: Person[];
  /**
   * Когда выпущена действующая ссылка и когда человек входил последний раз (ТЗ 3.8).
   * Последний вход — по всем сессиям, и по погашенным тоже: после перевыпуска или истечения
   * он не пропадает. Устройства — `/api/access/sessions`.
   */
  /** Ссылки ещё не выпускали — даты выпуска нет. */
  links: { role: Role; issued_at: string | null; last_login_at: string | null }[];
  is_demo: boolean;
}
