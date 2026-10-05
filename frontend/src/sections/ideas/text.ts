/**
 * Тексты раздела «Идеи и карты», которые собираются из чисел сервера.
 */

import type { TFunction } from 'i18next';

import type { AwaitingAnswer, Idea, MapNode } from './model';

/** «2 идеи ждут вашего „да“» и «дольше всех — 9 дн.». */
export function awaitingText(
  t: TFunction,
  answer: AwaitingAnswer,
): { main: string; detail: string | null } {
  if (answer.count === 0) return { main: t('ideas.awaiting.none'), detail: null };
  return {
    main: t('ideas.awaiting.main', { count: answer.count }),
    detail: t('ideas.awaiting.oldest', { count: answer.oldest_days }),
  };
}

/** Подпись идеи: автор, дата записи, сколько ждёт. */
export function ideaMeta(t: TFunction, idea: Idea, date: string): string {
  const parts = [t(`role.${idea.author}`), date];
  if (idea.step === 'review') parts.push(t('ideas.waiting', { count: idea.waiting_days }));
  return parts.join(' · ');
}

/** Узел и все его потомки — их нельзя назначить родителем: связи замкнулись бы в кольцо. */
export function descendants(nodes: readonly MapNode[], root: string): Set<string> {
  const children = new Map<string, string[]>();
  for (const node of nodes) {
    if (node.parent_id)
      children.set(node.parent_id, [...(children.get(node.parent_id) ?? []), node.id]);
  }
  const found = new Set([root]);
  const stack = [root];
  while (stack.length > 0) {
    for (const child of children.get(stack.pop()!) ?? []) {
      if (!found.has(child)) {
        found.add(child);
        stack.push(child);
      }
    }
  }
  return found;
}
