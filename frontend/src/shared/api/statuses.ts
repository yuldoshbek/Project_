/**
 * Названия и порядок статусов — из справочника, а не из кода (ТЗ 3.9; CLAUDE.md: справочники
 * статусов — редактируемые данные). Помощник переименовывает и переставляет статусы в
 * «Управлении», и это видно на всех экранах, а не только там.
 *
 * Код статуса остаётся в коде: по нему работают переходы и правила — терминальность,
 * причина паузы. Пока справочник не пришёл или в нём нет строки — ключ перевода с тем же
 * названием, что у наполнения (`app.seed`).
 */

import { useQuery } from '@tanstack/react-query';
import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';

import { dictionariesQuery } from './queries';

type StatusKind = 'project_statuses' | 'task_statuses';

const SECTION: Record<StatusKind, 'projects' | 'tasks'> = {
  project_statuses: 'projects',
  task_statuses: 'tasks',
};

export function useStatuses(kind: StatusKind) {
  const { t } = useTranslation();
  const entries = useQuery(dictionariesQuery()).data?.[kind];

  const name = useCallback(
    (code: string): string =>
      entries?.find((entry) => entry.code === code)?.name.ru ??
      t(`${SECTION[kind]}.statuses.${code}`),
    [entries, kind, t],
  );

  /** Коды в порядке справочника; без справочника — в том порядке, в каком пришли. */
  const ordered = useCallback(
    <S extends string>(codes: readonly S[]): S[] => {
      const rank = new Map(entries?.map((entry) => [entry.code, entry.sort_order]));
      return [...codes].sort((a, b) => (rank.get(a) ?? 0) - (rank.get(b) ?? 0));
    },
    [entries],
  );

  return { name, ordered };
}
