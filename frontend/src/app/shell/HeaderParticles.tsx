/**
 * Мягкие частицы в шапке — «космос» акцентом (ТЗ 6): только на ноутбуке и мониторе и только
 * в пустой середине шапки, между названием и кнопками. Под текстом и цифрами частиц нет.
 *
 * Места частиц заданы списком, а не случайно: одинаковая шапка на каждом экране и
 * одинаковые снимки экранов в тестах. Это CSS, а не сцена: дюжина точек и одна анимация.
 * `prefers-reduced-motion` их останавливает общим правилом в `app.css`.
 */

const DOTS = [
  { left: 6, top: 30, size: 3, delay: 0 },
  { left: 14, top: 62, size: 2, delay: 1.4 },
  { left: 23, top: 22, size: 2, delay: 3.1 },
  { left: 31, top: 70, size: 3, delay: 0.7 },
  { left: 40, top: 40, size: 2, delay: 2.2 },
  { left: 48, top: 18, size: 2, delay: 4.0 },
  { left: 57, top: 58, size: 3, delay: 1.0 },
  { left: 65, top: 28, size: 2, delay: 2.8 },
  { left: 73, top: 66, size: 2, delay: 0.3 },
  { left: 81, top: 36, size: 3, delay: 3.6 },
  { left: 89, top: 20, size: 2, delay: 1.8 },
  { left: 95, top: 60, size: 2, delay: 4.6 },
] as const;

export function HeaderParticles() {
  return (
    <div aria-hidden="true" className="pointer-events-none relative h-full min-w-0 flex-1">
      {DOTS.map((dot) => (
        <span
          key={`${dot.left}-${dot.top}`}
          className="absolute animate-twinkle rounded-full bg-space-glow opacity-0"
          style={{
            left: `${dot.left}%`,
            top: `${dot.top}%`,
            width: dot.size,
            height: dot.size,
            animationDelay: `${dot.delay}s`,
          }}
        />
      ))}
    </div>
  );
}
