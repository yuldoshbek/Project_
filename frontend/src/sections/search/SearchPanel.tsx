/**
 * Поиск по всем разделам (ТЗ 6: «поиск и кнопка захвата на каждом экране», V19).
 *
 * Одна строка ввода и находки по разделам. Касание находки открывает карточку в её
 * разделе (`targetOf`), панель закрывается. На телефоне панель — лист из нижней панели, на
 * ноутбуке и мониторе — лист по кнопке в верхней строке или клавише «/».
 *
 * Запрос уходит не на каждый знак, а после паузы набора: поиск зовут, пока человек ещё
 * печатает, и десять запросов на одно слово — это десять задержек до сервера впустую.
 */

import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { Search } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { describeError, request } from '@/shared/api/client';
import { Empty, Failure } from '@/shared/ui/States';

import { MIN_LENGTH, targetOf, type SearchHit, type HitKind, type SearchView } from './model';

/** Пауза набора, после которой уходит запрос. */
const TYPING_PAUSE_MS = 250;

function useDebounced(value: string, delay: number): string {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return settled;
}

export default function SearchPanel({ onPick }: { onPick: () => void }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [text, setText] = useState('');
  const query = useDebounced(text.trim(), TYPING_PAUSE_MS);
  const ready = query.length >= MIN_LENGTH;

  const result = useQuery({
    queryKey: ['search', query],
    queryFn: () => request<SearchView>(`/api/v1/search?q=${encodeURIComponent(query)}`),
    enabled: ready,
    // Пока идёт новый запрос, видны прежние находки, а не пустое место: список не мигает
    // на каждом знаке. Опрос, который стоит у данных разделов, поиску не нужен.
    placeholderData: keepPreviousData,
    refetchInterval: false,
  });

  const pick = (kind: HitKind, hit: SearchHit) => {
    void navigate(targetOf(kind, hit.id));
    onPick();
  };

  // Ввод — первая находка: набрал номер целиком, нажал «Ввод», карточка открыта.
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const first = result.data?.groups[0];
    const hit = first?.hits[0];
    if (first && hit) pick(first.kind, hit);
  };

  const groups = ready ? (result.data?.groups ?? []) : [];

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold text-ink-strong">{t('search.title')}</h2>
      <form onSubmit={submit} role="search">
        <label className="flex min-h-touch items-center gap-2 rounded-[var(--radius)] border border-line-strong bg-card px-3 focus-within:border-accent">
          <Search className="size-5 shrink-0 text-ink-muted" aria-hidden="true" />
          <input
            type="search"
            value={text}
            onChange={(event) => setText(event.target.value)}
            // Лист открывают ради ввода: фокус сразу в поле, на телефоне сразу клавиатура.
            autoFocus
            enterKeyHint="search"
            aria-label={t('search.label')}
            placeholder={t('search.placeholder')}
            className="min-w-0 flex-1 bg-transparent py-2 text-[15px] text-ink outline-none placeholder:text-ink-muted"
          />
        </label>
      </form>

      {!ready ? (
        <p className="text-sm text-ink-muted">{t('search.hint')}</p>
      ) : result.isError ? (
        <Failure detail={describeError(result.error)} onRetry={() => void result.refetch()} />
      ) : result.isPending ? (
        <p className="text-sm text-ink-muted">{t('search.loading')}</p>
      ) : groups.length === 0 ? (
        <Empty label={t('search.none', { query })} />
      ) : (
        <div className="flex flex-col gap-4">
          {groups.map((group) => (
            <section key={group.kind} aria-label={t(`search.kinds.${group.kind}`)}>
              <h3 className="text-xs font-semibold tracking-wide text-ink-muted uppercase">
                {t(`search.kinds.${group.kind}`)}
              </h3>
              <ul className="mt-1 flex flex-col">
                {group.hits.map((hit) => {
                  const meta = [hit.code, hit.context].filter(Boolean).join(' · ');
                  return (
                    <li key={hit.id}>
                      <button
                        type="button"
                        onClick={() => pick(group.kind, hit)}
                        className="flex min-h-touch w-full flex-col justify-center rounded-[var(--radius)] px-2 py-1.5 text-left hover:bg-hover"
                      >
                        <span className="line-clamp-2 text-[15px] leading-snug text-ink-strong">
                          {hit.title}
                        </span>
                        {meta ? (
                          <span className="numeric truncate text-xs text-ink-muted">{meta}</span>
                        ) : null}
                      </button>
                    </li>
                  );
                })}
              </ul>
              {group.more ? (
                <p className="px-2 text-xs text-ink-muted">{t('search.more')}</p>
              ) : null}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
