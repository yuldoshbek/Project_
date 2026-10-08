/**
 * Данные Пульта и три действия над ними: решить, спросить, отменить.
 *
 * Запрос — `GET /api/v1/pult`, опрос по умолчанию раз в 15 секунд (ADR-0034,
 * `shared/api/queries.ts`). После действия лестница перечитывается у сервера: экран не
 * пересчитывает счётчики сам (инвариант 2).
 *
 * Решение и вопрос возвращают идентификатор записи — его держит кнопка «Отменить»:
 * отмена — это удаление ровно того, что создано этим касанием, а не «последнего вообще».
 */

import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';

import { ApiError, request } from '@/shared/api/client';

import {
  NoWorkerError,
  currentSubscription,
  deviceSetup,
  isAppleMobile,
  readEnvironment,
  subscribe,
  subscriptionBody,
  workerRegistration,
  type DeviceSetup,
} from '@/app/notifications';

import type {
  DecisionKind,
  PultView,
  ReportPeriod,
  ReportView,
  SummaryView,
  TargetType,
} from './model';

export function pultQuery() {
  return queryOptions({
    queryKey: ['pult'],
    queryFn: () => request<PultView>('/api/v1/pult'),
  });
}

/** Отчёт недели или месяца. Не опрашивается: это документ на момент формирования. */
export function reportQuery(period: ReportPeriod, offset: number) {
  return queryOptions({
    queryKey: ['pult', 'report', period, offset],
    queryFn: () => request<ReportView>('/api/v1/pult/report', { query: { period, offset } }),
    refetchInterval: false,
    staleTime: 60_000,
  });
}

export function usePult() {
  return useQuery(pultQuery());
}

/**
 * Утренняя сводка. Под ключом Пульта: решение из сводки перечитывает её вместе с лестницей.
 *
 * Ключ не зависит от `as_of`: оно новое в каждом ответе, и под новым ключом вкладка каждые 15
 * секунд уходила бы в «загрузку» — строка сворачивалась, черновик вопроса пропадал.
 */
export function summaryQuery() {
  return queryOptions({
    queryKey: ['pult', 'summary'],
    queryFn: () => request<SummaryView>('/api/v1/pult/summary'),
  });
}

export function useSummary() {
  return useQuery(summaryQuery());
}

const DEVICE_KEY = ['pult', 'device'];

interface DeviceState {
  setup: DeviceSetup;
  apple: boolean;
  /** У страницы есть service worker: без него подписаться не на что (сервер разработки). */
  worker: boolean;
  /** С какого дня сервер доставляет сюда уведомления; `null` — сюда не доставляет. */
  enabledOn: string | null;
}

interface Subscribed {
  since: string;
  device: string;
}

/**
 * Сказать серверу, куда доставлять. Запрос идемпотентен: одна подписка — одна запись, сколько
 * раз её ни присылай.
 */
function save(subscription: PushSubscription): Promise<Subscribed> {
  return request<Subscribed>('/api/v1/push/subscription', {
    method: 'PUT',
    body: subscriptionBody(subscription),
  });
}

/**
 * Сверить подписку браузера с сервером: с какого дня он сюда доставляет; `null` — не доставляет.
 *
 * 410 — служба пушей уже ответила серверу, что этого адреса нет, а браузер всё ещё отдаёт ту же
 * подписку (Chrome не сообщает об отзыве). Сервер её не восстанавливает, и держать её незачем:
 * снятая, она уступает место кнопке «Включить уведомления», а та создаст новый адрес. Сама
 * вкладка не подписывается заново: на iPhone подписка возможна только по касанию человека.
 */
async function sync(subscription: PushSubscription): Promise<string | null> {
  try {
    return (await save(subscription)).since;
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 410) throw error;
    await subscription.unsubscribe();
    return null;
  }
}

/**
 * Уведомления на этом устройстве: можно ли их включить и включены ли.
 *
 * «Включены» говорит сервер, а не браузер: подписка браузера есть и после перевыпуска ссылки,
 * который стирает подписки на сервере, и после смены ключа. Поэтому при каждом открытии
 * вкладки существующая подписка отправляется серверу ещё раз — он восстанавливает запись и
 * отвечает, с какого дня доставляет. Опроса нет, но при возврате в приложение состояние
 * перечитывается: разрешение могли снять в настройках телефона.
 */
export function useThisDevice(pushKey: string | null) {
  const client = useQueryClient();
  const state = useQuery({
    queryKey: [...DEVICE_KEY, pushKey],
    queryFn: async (): Promise<DeviceState> => {
      const environment = readEnvironment();
      const setup = deviceSetup(environment);
      const apple = isAppleMobile(environment);
      if (setup !== 'ready') return { setup, apple, worker: false, enabledOn: null };

      const registration = await workerRegistration();
      if (!registration) return { setup, apple, worker: false, enabledOn: null };
      if (environment.permission !== 'granted' || !pushKey) {
        return { setup, apple, worker: true, enabledOn: null };
      }
      const subscription = await currentSubscription(registration, pushKey);
      const enabledOn = subscription ? await sync(subscription) : null;
      return { setup, apple, worker: true, enabledOn };
    },
    refetchInterval: false,
  });
  const enable = useMutation({
    mutationFn: async () => {
      // Кнопки нет, пока ключа нет (`Summary.tsx`); проверка — для типов.
      if (!pushKey) return;
      // Не разрешили — ничего не подписываем: карточка перечитает разрешение и скажет, как
      // его вернуть.
      if ((await Notification.requestPermission()) !== 'granted') return;
      const registration = await workerRegistration();
      if (!registration) throw new NoWorkerError();
      await save(await subscribe(registration, pushKey));
    },
    // Сводка перечитывается ради устройства руководителя: помощник видит его там же.
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: DEVICE_KEY }),
        client.invalidateQueries({ queryKey: summaryQuery().queryKey }),
      ]),
  });

  // Сбой включения устаревает, как только сервер сказал «доставляю сюда»: например, запись
  // подписки один раз не прошла, а перечитанное состояние её уже сохранило. Иначе отказ висел
  // бы под «Включены» до перезагрузки — и всплыл бы снова, если подписку потом отзовут.
  const enabledOn = state.data?.enabledOn ?? null;
  const { isError, reset } = enable;
  useEffect(() => {
    if (enabledOn && isError) reset();
  }, [enabledOn, isError, reset]);

  return { state, enable };
}

export interface Target {
  target_type: TargetType;
  target_id: string;
}

export type PultAction =
  | { type: 'decide'; target: Target; kind: DecisionKind }
  | { type: 'ask'; target: Target; text: string }
  | { type: 'undo-decision'; id: string }
  | { type: 'undo-question'; id: string };

async function perform(action: PultAction): Promise<string | null> {
  switch (action.type) {
    case 'decide':
      return (
        await request<{ id: string }>('/api/v1/decisions', {
          method: 'POST',
          body: { ...action.target, kind: action.kind },
        })
      ).id;
    case 'ask':
      return (
        await request<{ id: string }>('/api/v1/questions', {
          method: 'POST',
          body: { ...action.target, text: action.text },
        })
      ).id;
    case 'undo-decision':
      await request(`/api/v1/decisions/${action.id}`, { method: 'DELETE' });
      return null;
    case 'undo-question':
      await request(`/api/v1/questions/${action.id}`, { method: 'DELETE' });
      return null;
  }
}

export function usePultAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: perform,
    // Решение со сроком встаёт в календарь, вопрос меняет ступень даты — те же числа.
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: pultQuery().queryKey }),
        client.invalidateQueries({ queryKey: ['calendar'] }),
      ]),
  });
}
