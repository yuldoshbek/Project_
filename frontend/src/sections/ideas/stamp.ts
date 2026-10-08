/**
 * Отпечаток ветви карты — узлы и их версии, как их видел человек перед удалением.
 *
 * Сервер считает то же самое (`app.domain.ideas.branch_stamp`) и удаляет ветвь, только если
 * отпечатки совпали. Одного числа узлов мало: переименованный или подменённый вторым
 * пользователем узел оставлял число прежним и уходил молча (найдено ревью правок).
 *
 * FNV-1a, 32 бита, по строке «id:версия» через запятую в порядке id — а не криптографическая
 * свёртка: защищаемся от гонки двух людей, а не от подделки, а синхронный расчёт одинаково
 * пишется в Python, в браузере и в тестах. Модуль без импортов — его берут и сценарии e2e.
 */

export function branchStamp(nodes: readonly { id: string; version: number }[]): string {
  const line = [...nodes]
    .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
    .map((each) => `${each.id}:${each.version}`)
    .join(',');
  let hash = 0x811c9dc5;
  for (const byte of new TextEncoder().encode(line)) {
    hash ^= byte;
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, '0');
}
