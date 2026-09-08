/**
 * Сборка className из нескольких значений.
 *
 * Нужна из-за `noUncheckedIndexedAccess`: обращение к классу CSS-модуля имеет тип
 * `string | undefined`, и без такой обёртки в разметку попадает строка «undefined».
 * Заодно снимает необходимость в тернарниках внутри JSX.
 */
export function cx(...values: (string | false | null | undefined)[]): string {
  return values.filter((value): value is string => Boolean(value)).join(' ');
}
