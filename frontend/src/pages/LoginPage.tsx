/**
 * Вход в систему.
 *
 * Отказ выглядит одинаково независимо от причины: неверный адрес и неверный пароль дают
 * один и тот же текст. Различие в сообщениях — способ узнать, какие адреса заведены
 * (ORB-006), и на стороне сервера оно уже устранено; здесь важно не восстановить его
 * обратно «удобной» подсказкой.
 *
 * Блокировка после пяти неудачных попыток — отдельное сообщение: это не «попробуйте
 * ещё», а «подождите», и человек должен понимать разницу, иначе будет жать кнопку.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useLocation } from 'react-router-dom';

import { HttpError } from '../shared/api/client';
import { useSession } from '../shared/auth/useSession';
import styles from './pages.module.css';

const LOCKED = 'account-locked';

export function LoginPage() {
  const { t } = useTranslation();
  const { status, signIn } = useSession();
  const location = useLocation();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (status === 'signed-in') {
    const from = (location.state as { from?: string } | null)?.from ?? '/';
    return <Navigate to={from} replace />;
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);

    try {
      await signIn(email, password);
    } catch (failure) {
      setError(
        failure instanceof HttpError && failure.type?.endsWith(LOCKED) === true
          ? t('login.locked')
          : t('login.failed'),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.loginShell}>
      <form className={styles.loginCard} onSubmit={submit}>
        <h1 className={styles.loginTitle}>{t('app.name')}</h1>
        <p className={styles.loginSubtitle}>{t('app.tagline')}</p>

        <label className={styles.field} htmlFor="email">
          <span className={styles.fieldLabel}>{t('login.email')}</span>
          <input
            id="email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => {
              setEmail(event.target.value);
            }}
            className={styles.input}
          />
        </label>

        <label className={styles.field} htmlFor="password">
          <span className={styles.fieldLabel}>{t('login.password')}</span>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
            }}
            className={styles.input}
          />
        </label>

        {error !== null && (
          <p className={styles.loginError} role="alert">
            {error}
          </p>
        )}

        <button type="submit" className={styles.primaryButton} disabled={busy}>
          {busy ? t('login.submitting') : t('login.submit')}
        </button>
      </form>
    </div>
  );
}
