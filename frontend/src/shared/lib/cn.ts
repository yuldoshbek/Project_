import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Склейка классов с разрешением конфликтов Tailwind.
 *
 * Нужна потому, что у компонента есть свои классы и есть переданные: без разрешения
 * побеждает не последний, а тот, что стоит позже в собранном файле стилей. Внешний
 * `p-0` тогда молча ничего не меняет — и правка «у этой кнопки убрать отступ» превращается
 * в поиск причины.
 */
export function cn(...classes: ClassValue[]): string {
  return twMerge(clsx(classes));
}
