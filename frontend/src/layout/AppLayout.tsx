import { useTranslation } from 'react-i18next';
import { Outlet } from 'react-router-dom';

import { BottomNav } from './BottomNav';
import { Breadcrumbs } from './Breadcrumbs';
import styles from './layout.module.css';
import { LocaleSwitcher } from './LocaleSwitcher';
import { ModeSwitcher } from './ModeSwitcher';
import { Sidebar } from './Sidebar';
import { ThemeSwitcher } from './ThemeSwitcher';

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
        {/* На телефоне бокового меню нет, и без названия непонятно, где ты находишься:
            это первое, что ищут глазами на чужом устройстве. На широком экране название
            стоит в боковом меню, и здесь оно было бы вторым. */}
        <span className={styles.headerBrand}>{t('app.name')}</span>
        <Breadcrumbs />
        <ThemeSwitcher />
        <LocaleSwitcher />
        <ModeSwitcher />
      </header>

      <main id="main" className={styles.main}>
        <div className={styles.content}>
          <Outlet />
        </div>
      </main>

      <BottomNav />
    </div>
  );
}
