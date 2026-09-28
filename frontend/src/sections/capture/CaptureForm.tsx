/**
 * Захват — быстрая запись одной кнопкой с любого экрана (ТЗ 6, 7).
 *
 * Тип выбирается одним касанием: задача, просьба руководителя, идея, письмо, мероприятие.
 * Текст — с клавиатуры или диктовкой телефона: микрофон клавиатуры iPhone и есть «голос»,
 * своего распознавания в системе нет (внешние модели сняты, CLAUDE.md). Срок, ответственного
 * и тип задачи система понимает из фразы тем же разбором, что и строка «Новая задача»
 * (`domain/capture.py`), — подсказку можно поправить до записи.
 *
 * Куда уходит запись — допущение V17: задача — сразу в «Задачи» настоящим API; просьба
 * руководителя — в «Задачи» с пометкой; идея, письмо и мероприятие — во входящие, пока их
 * разделы не появятся. Фото — с хранилищем файлов в блоке 2 (V18): кнопка на месте и
 * говорит, когда заработает. Руководителю — два типа, свои: просьба и идея (ТЗ 6).
 *
 * Лист не закрывается после записи: после совещания записывают несколько дел подряд, и
 * каждое открытие листа — лишнее касание. Записывает Enter, как у строки «Новая задача»
 * (Shift+Enter — новая строка): на телефоне это клавиша «отправить» клавиатуры, и клавиатура
 * не прячется, — а кнопка «Записать» под четырьмя полями разбора оказывается под ней.
 */

import { Camera, Mic, Sparkles } from 'lucide-react';
import { useId, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';

import { useDevice } from '@/app/device';
import { useCurrentUser } from '@/app/session';
import { ParsedFields } from '@/sections/tasks/ParsedFields';
import { useLineParse, type ParsedField } from '@/sections/tasks/useLineParse';
import { tasksQuery, useCreateTask } from '@/sections/tasks/useTasks';
import { describeError } from '@/shared/api/client';
import { cn } from '@/shared/lib/cn';
import { Button } from '@/shared/ui/Button';
import { Signal } from '@/shared/ui/Signal';
import { Failure } from '@/shared/ui/States';

import { KIND_ICON } from './kinds';
import { CAPTURE_KINDS, type CaptureKind } from './model';
import { Recent } from './Recent';
import { useCaptures, useRememberTask, useSaveCapture } from './useCapture';

const LEADER_KINDS: readonly CaptureKind[] = ['request', 'idea'];

/** Поля разбора по типу: у задачи — все четыре, у письма — один срок ответа, у идеи — нет. */
const FIELDS: Record<CaptureKind, readonly ParsedField[]> = {
  task: ['type', 'due', 'assignee', 'project'],
  request: ['due', 'assignee'],
  idea: [],
  letter: ['due'],
  event: ['due'],
};

const REMEMBERED = 'orbita.capture.kind';

function remembered(allowed: readonly CaptureKind[], fallback: CaptureKind): CaptureKind {
  try {
    const stored = localStorage.getItem(REMEMBERED) as CaptureKind | null;
    return stored && allowed.includes(stored) ? stored : fallback;
  } catch {
    return fallback;
  }
}

function remember(kind: CaptureKind) {
  try {
    localStorage.setItem(REMEMBERED, kind);
  } catch {
    // Без хранилища тип просто не запоминается: в следующий раз — по умолчанию.
  }
}

export function CaptureForm() {
  const { t } = useTranslation();
  const ids = useId();
  const device = useDevice();
  const user = useCurrentUser();
  const author = user.data?.role === 'leader' ? 'leader' : 'assistant';
  const kinds = author === 'leader' ? LEADER_KINDS : CAPTURE_KINDS;
  // Руководитель на телефоне «записывает идею» (ТЗ 6), помощник — заводит работу.
  const fallback: CaptureKind = author === 'leader' ? 'idea' : 'task';
  const [chosen, setKind] = useState<CaptureKind | null>(null);
  // Тип — из разрешённых роли: выбранный раньше тип чужой роли не остаётся выбранным.
  const kind = chosen && kinds.includes(chosen) ? chosen : remembered(kinds, fallback);
  const [text, setText] = useState('');
  const [saved, setSaved] = useState<string | null>(null);
  const field = useRef<HTMLTextAreaElement>(null);

  const fields = FIELDS[kind];
  const line = useLineParse(text, fields.length > 0);
  const dictionaries = useQuery({ ...tasksQuery(), enabled: fields.includes('assignee') });
  const createTask = useCreateTask();
  const save = useSaveCapture(author);
  const rememberTask = useRememberTask(author);
  const demo = useCaptures().data?.is_demo ?? false;
  const pending = createTask.isPending || save.isPending;
  const failure = createTask.error ?? save.error;
  const title = kind === 'task' || kind === 'request' ? line.title : text.trim();
  const labels: Partial<Record<ParsedField, string>> = {};
  if (kind === 'request') labels.assignee = t('capture.fields.to');
  if (kind === 'letter') labels.due = t('capture.fields.answerBy');
  if (kind === 'event') labels.due = t('capture.fields.date');

  // Ошибка прошлой записи не остаётся рядом с успехом следующей другого типа.
  const forget = () => {
    createTask.reset();
    save.reset();
  };

  const choose = (next: CaptureKind) => {
    setKind(next);
    remember(next);
    setSaved(null);
    forget();
    line.clearManual();
  };

  /**
   * Курсор возвращается в поле: следующее дело записывают сразу. Пока запись шла по сети,
   * могли начать следующее — набранное не стирается. На iPhone после касания «Записать»
   * клавиатура сама не вернётся (фокус из ответа сети, а не из касания) — поэтому Enter.
   */
  const done = (message: string, sent: string) => {
    setSaved(message);
    if (field.current && field.current.value !== sent) return;
    setText('');
    line.reset();
    field.current?.focus();
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!title || pending) return;
    const sent = text;
    const due = line.value('due') || null;
    forget();
    if (kind === 'task') {
      createTask.mutate(
        {
          title,
          type_code: line.value('type') || null,
          due_on: due,
          assignee_id: line.value('assignee') || null,
          project_id: line.value('project') || null,
        },
        {
          onSuccess: (task) => {
            rememberTask(task.title, due);
            done(t('capture.saved.task', { code: task.code }), sent);
          },
        },
      );
      return;
    }
    save.mutate(
      {
        kind,
        text: title,
        due_on: fields.includes('due') ? due : null,
        assignee_id: kind === 'request' ? line.value('assignee') || null : null,
      },
      { onSuccess: () => done(t(`capture.saved.${kind}`), sent) },
    );
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // Посреди набора иероглифов или подбора слова Enter выбирает вариант, а не записывает.
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  };

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col gap-1">
        <span className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold text-ink-strong">{t('capture.title')}</h2>
          {demo ? <Signal state="wait">{t('pult.demo')}</Signal> : null}
        </span>
        <p className="text-sm text-ink-muted">{t('capture.question')}</p>
        {/* Подсказка видна, а не во всплывающем title: на телефоне наведения нет. */}
        {demo ? <p className="text-xs text-ink-muted">{t('capture.demoHint')}</p> : null}
      </header>

      <form onSubmit={submit} className="flex flex-col gap-3">
        <fieldset className="flex flex-col gap-1.5">
          <legend className="mb-1 text-sm text-ink">{t('capture.kindLabel')}</legend>
          <span className="flex flex-wrap gap-2">
            {kinds.map((each) => {
              const Icon = KIND_ICON[each];
              return (
                <label
                  key={each}
                  className={cn(
                    'inline-flex min-h-touch cursor-pointer items-center gap-1.5 rounded-[var(--radius-pill)] border px-3 text-sm md:min-h-9',
                    // Сам переключатель спрятан, и обводку фокуса рисует подпись (ТЗ 9).
                    'has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent',
                    kind === each
                      ? 'border-line-accent bg-accent-soft text-accent-ink'
                      : 'border-line bg-card text-ink',
                  )}
                >
                  <input
                    type="radio"
                    name={`${ids}-kind`}
                    value={each}
                    checked={kind === each}
                    onChange={() => choose(each)}
                    className="sr-only"
                  />
                  <Icon className="size-4" aria-hidden="true" />
                  {t(`capture.kinds.${each}`)}
                </label>
              );
            })}
          </span>
          <span className="text-xs text-ink-muted">{t(`capture.where.${kind}`)}</span>
        </fieldset>

        <label className="flex flex-col gap-1 text-sm text-ink">
          <span className="sr-only">{t('capture.text')}</span>
          <textarea
            // Захват — ради скорости: курсор сразу в поле, на телефоне сразу клавиатура.
            autoFocus
            ref={field}
            value={text}
            onChange={(event) => {
              setText(event.target.value);
              setSaved(null);
              if (!event.target.value.trim()) line.clearManual();
            }}
            onKeyDown={onKeyDown}
            enterKeyHint="send"
            rows={3}
            placeholder={t(`capture.placeholders.${kind}`)}
            className="min-h-24 w-full resize-y rounded-[var(--radius)] border border-line-strong bg-card px-3 py-2 text-[15px] text-ink"
          />
        </label>

        {(kind === 'task' || kind === 'request') && line.parsed && title !== text.trim() ? (
          <p className="flex items-center gap-1.5 text-xs text-ink-muted">
            <Sparkles className="size-3.5 shrink-0 text-accent-ink" aria-hidden="true" />
            <span className="min-w-0">{t('tasks.capture.understoodAs', { title })}</span>
          </p>
        ) : null}

        {text.trim() && fields.length > 0 ? (
          <ParsedFields
            line={line}
            fields={fields}
            types={dictionaries.data?.types ?? []}
            people={dictionaries.data?.people ?? []}
            projects={dictionaries.data?.projects ?? []}
            layout={device === 'phone' ? 'stack' : 'pairs'}
            labels={labels}
          />
        ) : null}

        <div className="flex flex-col gap-1.5">
          <span className="flex flex-wrap items-center gap-2">
            <Button type="submit" look="primary" disabled={!title || pending}>
              {t('capture.save')}
            </Button>
            <Button type="button" disabled aria-describedby={`${ids}-photo`}>
              <Camera className="size-4" aria-hidden="true" />
              {t('capture.photo')}
            </Button>
          </span>
          <span id={`${ids}-photo`} className="text-xs text-ink-muted">
            {t('capture.photoLater')}
          </span>
          {device === 'phone' ? (
            <span className="flex items-center gap-1.5 text-xs text-ink-muted">
              <Mic className="size-3.5" aria-hidden="true" />
              {t('capture.dictation')}
            </span>
          ) : null}
        </div>

        {saved ? (
          <p
            role="status"
            className="rounded-[var(--radius)] bg-calm-soft px-3 py-2 text-sm text-calm-ink"
          >
            {saved}
          </p>
        ) : null}
        {failure ? <Failure detail={describeError(failure)} /> : null}
      </form>

      <Recent />
    </div>
  );
}
