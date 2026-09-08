import { useTranslation } from 'react-i18next';
import { Outlet } from 'react-router-dom';

import { Breadcrumbs } from './Breadcrumbs';
import styles from './layout.module.css';
import { LocaleSwitcher } from './LocaleSwitcher';
import { Sidebar } from './Sidebar';

/**
 * Оболочка приложения: боковое меню, шапка с хлебными крошками, область содержимого.
 *
 * Экраны подставляются через `Outlet` — разметка одна на всё приложение, чтобы
 * переключение раздела не перерисовывало меню и не сбрасывало прокрутку.
 */
export function AppLayout() {
  const { t } = useTranslation();

  return (
    <div className={styles.shell}>
      <a href="#main" className={styles.skipLink}>
        {t('app.skipToContent')}
      </a>

      <Sidebar />

      <header className={styles.header}>
        <Breadcrumbs />
        <LocaleSwitcher />
      </header>

      <main id="main" className={styles.main}>
        <div className={styles.content}>
          <Outlet />
        </div>
      </main>
    </div>
  );
}
