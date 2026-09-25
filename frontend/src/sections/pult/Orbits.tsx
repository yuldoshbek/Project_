/**
 * Орбитальные дуги в шапке Пульта — «космос» акцентом (ТЗ 6, решение заказчика 25.09).
 *
 * Только на ноутбуке и мониторе и только в своей колонке шапки: под цифрами и текстом
 * украшения нет никогда. Это SVG и CSS-вращение, а не сцена: ни одного байта three.js,
 * вес — несколько сотен байт, первый экран телефона от него не зависит вовсе.
 *
 * Цвет — токен `--space-glow` через `currentColor`, поэтому обе темы получают свою орбиту
 * без второго набора значений. `prefers-reduced-motion` останавливает вращение общим
 * правилом в `app.css`.
 */

export function Orbits({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 240 120" className={className} aria-hidden="true" focusable="false">
      <g className="text-space-glow" fill="none" stroke="currentColor">
        <g className="origin-center animate-orbit" style={{ transformBox: 'fill-box' }}>
          <ellipse cx="120" cy="60" rx="108" ry="34" strokeOpacity="0.28" strokeWidth="1" />
          <circle cx="228" cy="60" r="3.5" fill="currentColor" stroke="none" />
        </g>
        <g className="origin-center animate-orbit-reverse" style={{ transformBox: 'fill-box' }}>
          <ellipse
            cx="120"
            cy="60"
            rx="74"
            ry="22"
            strokeOpacity="0.4"
            strokeWidth="1"
            strokeDasharray="2 5"
          />
          <circle cx="46" cy="60" r="2.5" fill="currentColor" stroke="none" fillOpacity="0.8" />
        </g>
        <circle cx="120" cy="60" r="9" fill="currentColor" fillOpacity="0.12" stroke="none" />
        <circle cx="120" cy="60" r="4" fill="currentColor" fillOpacity="0.55" stroke="none" />
      </g>
    </svg>
  );
}
