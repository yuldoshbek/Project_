import styles from './ui.module.css';

interface SkeletonProps {
  /** Высота блока в пикселях. */
  height?: number;
  /** Ширина: строка CSS, по умолчанию во всю доступную. */
  width?: string;
  /** Число повторов — для списков и таблиц. */
  count?: number;
}

/**
 * Заглушка на время загрузки.
 *
 * Скрыта от программ чтения с экрана: о загрузке им сообщает `aria-busy` на области
 * содержимого, а мерцающие прямоугольники в озвучке только мешают.
 */
export function Skeleton({ height = 16, width = '100%', count = 1 }: SkeletonProps) {
  return (
    <>
      {Array.from({ length: count }, (_, index) => (
        <div
          key={index}
          className={styles.skeleton}
          style={{ height, width, marginBottom: count > 1 ? 'var(--space-2)' : undefined }}
          aria-hidden="true"
        />
      ))}
    </>
  );
}
