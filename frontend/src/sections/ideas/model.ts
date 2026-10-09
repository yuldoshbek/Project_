/**
 * Идеи и карты — договор данных раздела: «что предложено и как это связано?» (ТЗ 2, 3.6).
 * Форма ответов `GET /api/v1/ideas` и `GET /api/v1/maps/{id}`.
 *
 * **Числа считает сервер** (инвариант 2): сколько дней идея ждёт руководителя, ответ «Что
 * ждёт моего „да“?», ступень связанного узла карты — та же, что на Пульте.
 *
 * Допущения (docs/OPEN-QUESTIONS.md): V46 — идея ждёт руководителя с момента отправки на
 * рассмотрение; V47 — «отложено» не тупик, отложенную можно отправить снова.
 */

import type { Step } from '@/sections/pult/model';

export type IdeaStep = 'draft' | 'review' | 'decided';

export type Outcome = 'project' | 'task' | 'postponed';

export type MapMode = 'sketch' | 'structure';

export const MAP_MODES: readonly MapMode[] = ['sketch', 'structure'];

/** Настоящая запись, с которой связаны идея или узел. */
export interface Link {
  type: 'project' | 'task';
  id: string;
  code: string;
  title: string;
}

export interface Idea {
  id: string;
  text: string;
  author: 'assistant' | 'leader';
  step: IdeaStep;
  outcome: Outcome | null;
  created_at: string;
  review_at: string | null;
  decided_at: string | null;
  /** Сколько дней ждёт руководителя; у не отправленной — 0 (V46). */
  waiting_days: number;
  link: Link | null;
  /** Фото, снятые вместе с идеей в Захвате (V18): приходят вместе со списком. */
  photos: { id: string; name: string }[];
  version: number;
}

export interface AwaitingAnswer {
  key: 'awaiting';
  count: number;
  oldest_days: number;
  oldest_id: string | null;
  /** Идеи на рассмотрении — дольше всех ждущая первой. */
  rows: string[];
}

export interface MapSummary {
  id: string;
  title: string;
  mode: MapMode;
  nodes: number;
  /** Узлов, связанных с проектом или задачей. */
  linked: number;
  changed_at: string;
  version: number;
}

export interface ProjectType {
  code: string;
  name: string;
}

export interface IdeasView {
  as_of: string;
  questions: AwaitingAnswer[];
  /** Новые первыми. */
  items: Idea[];
  maps: MapSummary[];
  project_types: ProjectType[];
  is_demo: boolean;
}

export interface MapNode {
  id: string;
  parent_id: string | null;
  text: string;
  x: number;
  y: number;
  link: Link | null;
  /** Ступень связанной записи — строка той же лестницы, что на Пульте. */
  step: Step | null;
  deviation: number;
  version: number;
}

export interface MapCard extends MapSummary {
  /** В порядке заведения — так идёт и контур на телефоне. */
  node_list: MapNode[];
  project_types: ProjectType[];
}

/** Размер узла на полотне: по нему рисуются связи от края до края. */
export const NODE_WIDTH = 200;
export const NODE_HEIGHT = 64;
