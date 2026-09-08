import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { ROUTES } from '../app/routes';
import styles from './pages.module.css';

/**
 * Нет доступа к проекту или задаче (ADR-0003, сценарий U7).
 *
 * Текст намеренно не сообщает, существует ли запрошенная запись: по ADR-0007 обращение
 * к чужому проекту отвечает 404, а не 403, чтобы не раскрывать сам факт его наличия.
 * Этот экран показывается там, где запись заведомо существует, но прав на неё нет —
 * например, участник проекта открывает действие, доступное только куратору.
 */
export function ForbiddenPage() {
  const { t } = useTranslation();

  return (
    <section className={styles.centered}>
      <h1 className={styles.centeredTitle}>{t('error.forbiddenTitle')}</h1>
      <p className={styles.centeredText}>{t('error.forbiddenText')}</p>
      <Link to={ROUTES.dashboard}>{t('error.goHome')}</Link>
    </section>
  );
}
