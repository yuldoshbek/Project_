import { useTranslation } from 'react-i18next';

import { Skeleton } from '../shared/ui/Skeleton';
import styles from './pages.module.css';

interface PlaceholderPageProps {
  titleKey: string;
  /** Тикет, в котором появится содержимое. Виден пользователю — это внутренняя система. */
  ticket: string;
}

/**
 * Временное содержимое раздела.
 *
 * Существует, чтобы каркас можно было пройти целиком до появления экранов: проверить
 * переходы, разметку и локализацию. Каждый такой экран заменяется своим тикетом
 * (`ORB-019`, `ORB-020` и так далее) — список в `app/routes.ts`.
 */
export function PlaceholderPage({ titleKey, ticket }: PlaceholderPageProps) {
  const { t } = useTranslation();

  return (
    <section className={styles.page}>
      <h1 className={styles.pageTitle}>{t(titleKey)}</h1>
      <p className={styles.pageHint}>{t('placeholder.title')}</p>
      <p className={styles.pageHint}>{t('placeholder.text', { ticket })}</p>
      <div className={styles.placeholderBlocks}>
        <Skeleton height={72} count={3} />
      </div>
    </section>
  );
}
