import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { ROUTES } from '../app/routes';
import styles from './pages.module.css';

export function NotFoundPage() {
  const { t } = useTranslation();

  return (
    <section className={styles.centered}>
      <h1 className={styles.centeredTitle}>{t('error.notFoundTitle')}</h1>
      <p className={styles.centeredText}>{t('error.notFoundText')}</p>
      <Link to={ROUTES.dashboard}>{t('error.goHome')}</Link>
    </section>
  );
}
