import { cx } from './cx';
import styles from './ui.module.css';

/**
 * Значения светофора актуальности (ТЗ 6.4, ADR-0005).
 *
 * Считаются на сервере одним правилом для проекта и задачи: если цвет вычислять в
 * интерфейсе, дашборд и списки разойдутся в оценке одной и той же записи.
 * Серый — завершённые и отменённые: они из светофора исключены.
 */
export type Health = 'green' | 'yellow' | 'red' | 'grey';

const HEALTH_CLASS: Record<Health, string | undefined> = {
  green: styles.healthGreen,
  yellow: styles.healthYellow,
  red: styles.healthRed,
  grey: styles.healthGrey,
};

interface HealthDotProps {
  health: Health;
  /** Подпись для программ чтения с экрана: цвет сам по себе не читается. */
  label: string;
}

export function HealthDot({ health, label }: HealthDotProps) {
  return (
    <span
      className={cx(styles.health, HEALTH_CLASS[health])}
      role="img"
      aria-label={label}
      title={label}
    />
  );
}
