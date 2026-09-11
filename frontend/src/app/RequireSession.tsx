/**
 * Ворота приложения: без действующей сессии дальше не пускают.
 *
 * Проверка стоит здесь, а не в каждом экране: экран, который забыли проверить, отдаёт
 * пустую страницу вместо данных, и выглядит это как поломка, а не как «войдите».
 *
 * Адрес, с которого человека увели, запоминается и возвращается после входа. Ссылка на
 * отфильтрованный портфель, присланная руководителю, обязана привести туда, куда вела, —
 * а не на дашборд с пожеланием поискать самому.
 */

import { useTranslation } from 'react-i18next';
import { Navigate, Outlet, useLocation } from 'react-router-dom';

import { useSession } from '../shared/auth/useSession';
import { ROUTES } from './routes';

export function RequireSession() {
  const { status } = useSession();
  const location = useLocation();
  const { t } = useTranslation();

  // Пока сессия восстанавливается, решение ещё не принято: показать экран входа тому,
  // кто уже вошёл, — значит мигать им при каждой перезагрузке.
  if (status === 'restoring') {
    return <p role="status">{t('state.loading')}</p>;
  }

  if (status === 'anonymous') {
    return (
      <Navigate to={ROUTES.login} replace state={{ from: location.pathname + location.search }} />
    );
  }

  return <Outlet />;
}
