/**
 * Сетка месяца: недели с понедельника, соседние месяцы по краям. Даты — строки
 * `YYYY-MM-DD`, счёт — в UTC: день в Ташкенте уже посчитан сервером, здесь только листают.
 */

const DAY_MS = 86_400_000;

function utc(date: string): Date {
  return new Date(`${date}T00:00:00Z`);
}

function iso(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function addDays(date: string, days: number): string {
  return iso(new Date(utc(date).getTime() + days * DAY_MS));
}

/** Месяц `YYYY-MM` через `count` месяцев. */
export function addMonths(month: string, count: number): string {
  const [year, index] = month.split('-').map(Number) as [number, number];
  const moved = new Date(Date.UTC(year, index - 1 + count, 1));
  return iso(moved).slice(0, 7);
}

/** День недели с понедельника: 0 — понедельник, 6 — воскресенье. */
export function weekday(date: string): number {
  return (utc(date).getUTCDay() + 6) % 7;
}

/** Дни сетки месяца — целыми неделями, с понедельника первой по воскресенье последней. */
export function monthRange(month: string): { from: string; to: string } {
  const first = `${month}-01`;
  const last = addDays(`${addMonths(month, 1)}-01`, -1);
  return { from: addDays(first, -weekday(first)), to: addDays(last, 6 - weekday(last)) };
}

export function weeksOf(range: { from: string; to: string }): string[][] {
  const weeks: string[][] = [];
  for (let day = range.from; day <= range.to; day = addDays(day, 7)) {
    weeks.push(Array.from({ length: 7 }, (_, index) => addDays(day, index)));
  }
  return weeks;
}
