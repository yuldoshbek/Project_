/**
 * Разбор фразы с правкой человека — общий для строки «Новая задача» и Захвата.
 *
 * Разбор идёт на сервере (`POST /api/v1/tasks/parse`, правила `domain/capture.py`) после
 * паузы набора. Подсказку можно поправить; поправленная перестаёт быть подсказкой, и новый
 * разбор её не трогает (инвариант 6: предложенное системой и внесённое человеком — разные
 * вещи). Одна логика на два места ввода, чтобы одна фраза не давала в них разный срок.
 */

import { useEffect, useState } from 'react';

import { useParse } from './useTasks';

/** Пауза набора, после которой строка разбирается. Короче — разбор мигает под пальцами. */
const PARSE_DELAY_MS = 250;

export type ParsedField = 'type' | 'due' | 'assignee' | 'project';

export function useLineParse(text: string, enabled = true) {
  const parse = useParse();
  const [manual, setManual] = useState<Partial<Record<ParsedField, string>>>({});

  useEffect(() => {
    if (!enabled || !text.trim()) return;
    const timer = window.setTimeout(() => parse.mutate(text), PARSE_DELAY_MS);
    return () => window.clearTimeout(timer);
    // `parse` — новый объект на каждый рендер; зависеть надо от текста.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, enabled]);

  // Ответ на устаревший текст не показывается: пока шёл разбор, строку могли дописать.
  const parsed = enabled && parse.data && parse.variables === text ? parse.data : null;

  const suggestedValue: Record<ParsedField, string | null> = {
    type: parsed?.type_code ?? null,
    due: parsed?.due_on ?? null,
    assignee: parsed?.assignee_id ?? null,
    project: null,
  };

  const value = (field: ParsedField) =>
    field in manual ? (manual[field] ?? '') : (suggestedValue[field] ?? '');

  return {
    parsed,
    /** Название без распознанных кусков — или сама фраза, пока разбора нет. */
    title: parsed?.title ?? text.trim(),
    value,
    set: (field: ParsedField, next: string) => setManual({ ...manual, [field]: next }),
    /** Подсказка разбора — ещё не тронутая человеком. */
    suggested: (field: ParsedField) => suggestedValue[field] !== null && !(field in manual),
    clearManual: () => setManual({}),
    reset: () => {
      setManual({});
      parse.reset();
    },
  };
}

export type LineParse = ReturnType<typeof useLineParse>;
