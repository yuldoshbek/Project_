/**
 * Вкладка «Загрузка»: таблица Word → предпросмотр классов изменений → применение (ТЗ 7).
 *
 * Классы — как в ТЗ: новые, без изменений, текст изменился, сменился ответственный, срок
 * сдвинут, исчезли, не распознано. Перенос срока записывается только подтверждённый
 * человеком и попадает в историю продлений; написание ФИО сопоставляет человек; повторная
 * загрузка той же таблицы ничего не меняет.
 *
 * На этом шаге файл не разбирается: экран на вымышленных данных показывает предпросмотр
 * образца по имени файла. Разбор Word — шаг API.
 */

import { Upload } from 'lucide-react';
import { useState, type DragEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { cn } from '@/shared/lib/cn';
import { formatDate } from '@/shared/time';
import { Button } from '@/shared/ui/Button';
import { Card } from '@/shared/ui/Card';
import { Failure, Loading } from '@/shared/ui/States';
import { Signal } from '@/shared/ui/Signal';
import { describeError } from '@/shared/api/client';

import {
  CHANGE_CLASSES,
  SOURCES,
  type ApplyChoices,
  type ApplyResult,
  type ExtensionKind,
  type IjroSource,
  type IjroView,
  type Preview,
  type PreviewRow,
  type UploadInput,
} from './model';
import { useApply, usePreview } from './useIjro';

/** Имя образца: таблица следующего квартала вымышленного реестра. */
const SAMPLE = 'АП топшириқлари 4-чорак.docx';

const NO_CHOICES: ApplyChoices = { due_moves: {}, aliases: {}, removed: [] };

const FIELD =
  'min-h-touch rounded-[var(--radius)] border border-line-strong bg-card px-2 text-sm text-ink';

export function UploadTab({ view }: { view: IjroView }) {
  const { t } = useTranslation();
  const [source, setSource] = useState<IjroSource>('pa');
  const [upload, setUpload] = useState<UploadInput | null>(null);
  const [choices, setChoices] = useState<ApplyChoices>(NO_CHOICES);
  const [result, setResult] = useState<ApplyResult | null>(null);
  const [over, setOver] = useState(false);
  const preview = usePreview(upload);
  const apply = useApply();

  const take = (name: string, size: number) => {
    setUpload({ file: { name, size }, source });
    setChoices(NO_CHOICES);
    setResult(null);
  };

  const drop = (event: DragEvent) => {
    event.preventDefault();
    setOver(false);
    const file = event.dataTransfer.files[0];
    if (file) take(file.name, file.size);
  };

  return (
    <div className="flex flex-col gap-4">
      <Card title={t('ijro.upload.title')} question={t('ijro.upload.question')}>
        <label
          onDragOver={(event) => {
            event.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={drop}
          className={cn(
            'flex min-h-28 cursor-pointer flex-col items-center justify-center gap-2',
            'rounded-[var(--radius-lg)] border border-dashed p-4 text-center text-sm',
            over ? 'border-accent bg-accent-soft text-accent-ink' : 'border-line-strong text-ink',
          )}
        >
          <Upload className="size-5" aria-hidden="true" />
          <span>{t('ijro.upload.drop')}</span>
          <input
            type="file"
            accept=".docx"
            className="sr-only"
            aria-label={t('ijro.upload.choose')}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) take(file.name, file.size);
            }}
          />
        </label>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <label className="text-xs text-ink-muted" htmlFor="ijro-source">
            {t('ijro.upload.source')}
          </label>
          <select
            id="ijro-source"
            className={FIELD}
            value={source}
            onChange={(event) => setSource(event.target.value as IjroSource)}
          >
            {SOURCES.map((each) => (
              <option key={each} value={each}>
                {t(`ijro.sources.${each}`)}
              </option>
            ))}
          </select>
          <Button size="small" onClick={() => take(SAMPLE, 48_000)}>
            {t('ijro.upload.sample')}
          </Button>
        </div>
        <p className="mt-2 text-xs text-ink-muted">{t('ijro.upload.demo')}</p>
      </Card>

      {upload ? (
        preview.isPending ? (
          <Loading />
        ) : preview.isError ? (
          <Failure detail={describeError(preview.error)} />
        ) : (
          <PreviewCard
            preview={preview.data}
            choices={choices}
            onChoices={setChoices}
            result={result}
            busy={apply.isPending}
            onApply={() =>
              apply.mutate({ upload, choices }, { onSuccess: (outcome) => setResult(outcome) })
            }
          />
        )
      ) : null}

      <Card title={t('ijro.upload.history.title')} question={t('ijro.upload.history.question')}>
        <ul className="divide-y divide-line text-sm">
          {view.batches.map((batch) => (
            <li key={batch.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2">
              <span className="min-w-0 flex-1 truncate text-ink-strong">{batch.file}</span>
              <span className="numeric text-xs text-ink-muted">
                {[
                  formatDate(batch.table_on),
                  t(`ijro.sources.${batch.source}`),
                  batch.counts.new > 0
                    ? t('ijro.upload.history.created', { count: batch.counts.new })
                    : null,
                  batch.counts.due_moved > 0
                    ? t('ijro.upload.history.moved', { count: batch.counts.due_moved })
                    : null,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function PreviewCard({
  preview,
  choices,
  onChoices,
  result,
  busy,
  onApply,
}: {
  preview: Preview;
  choices: ApplyChoices;
  onChoices: (choices: ApplyChoices) => void;
  result: ApplyResult | null;
  busy: boolean;
  onApply: () => void;
}) {
  const { t } = useTranslation();

  if (preview.already_applied_on) {
    return (
      <Card title={preview.file}>
        {result?.outcome === 'applied' ? <Outcome result={result} /> : null}
        <p className="text-sm text-ink">
          {t('ijro.upload.already', { date: formatDate(preview.already_applied_on) })}
        </p>
      </Card>
    );
  }

  const groups = CHANGE_CLASSES.filter((name) => name !== 'unchanged' && preview.counts[name] > 0);

  return (
    <Card
      title={preview.file}
      question={t('ijro.upload.preview.question', { year: preview.table_year })}
    >
      <ul className="flex flex-wrap gap-2">
        {CHANGE_CLASSES.map((name) => (
          <li key={name}>
            <Signal state={name === 'unrecognized' || name === 'vanished' ? 'wait' : 'plain'}>
              {t(`ijro.upload.classes.${name}`, { count: preview.counts[name] })}
            </Signal>
          </li>
        ))}
      </ul>

      {groups.length === 0 ? (
        <p className="mt-3 text-sm text-ink">{t('ijro.upload.preview.nothing')}</p>
      ) : (
        groups.map((name) => (
          <section key={name} className="mt-4">
            <h3 className="text-sm font-semibold text-ink-strong">
              {t(`ijro.upload.groups.${name}`)}
            </h3>
            <ul className="mt-1 divide-y divide-line">
              {preview.rows
                .filter((row) => row.class === name)
                .map((row) => (
                  <PreviewLine key={row.id} row={row} choices={choices} onChoices={onChoices} />
                ))}
            </ul>
          </section>
        ))
      )}

      {result ? <Outcome result={result} /> : null}
      {groups.length > 0 ? (
        <div className="mt-4">
          <Button look="primary" disabled={busy} onClick={onApply}>
            {t('ijro.upload.apply')}
          </Button>
        </div>
      ) : null}
    </Card>
  );
}

function Outcome({ result }: { result: ApplyResult }) {
  const { t } = useTranslation();
  return (
    <p className="mt-3 mb-2 text-sm font-medium text-calm-ink" role="status">
      {result.outcome === 'applied'
        ? t('ijro.upload.result.applied', {
            created: result.created,
            changed: result.changed,
            extensions: result.extensions,
            pending: result.pending_extensions,
          })
        : result.outcome === 'already_applied'
          ? t('ijro.upload.already', { date: formatDate(result.applied_on) })
          : t('ijro.upload.result.noChanges')}
    </p>
  );
}

function PreviewLine({
  row,
  choices,
  onChoices,
}: {
  row: PreviewRow;
  choices: ApplyChoices;
  onChoices: (choices: ApplyChoices) => void;
}) {
  const { t } = useTranslation();
  const where = [row.document_code, row.band].filter(Boolean).join(' · ');
  const confirmed = choices.due_moves[row.id];
  const alias = choices.aliases[row.id];

  const setMove = (kind: ExtensionKind | null) => {
    const due_moves = { ...choices.due_moves };
    if (kind) due_moves[row.id] = kind;
    else delete due_moves[row.id];
    onChoices({ ...choices, due_moves });
  };

  return (
    <li className="py-2 text-sm">
      {where ? <p className="numeric text-xs text-ink-muted">{where}</p> : null}
      {row.raw ? (
        <p className="numeric text-ink">{row.raw}</p>
      ) : row.diff ? (
        <p className="text-ink">
          <span className="text-ink-muted line-through">{row.diff.from}</span>
          <span className="block text-ink-strong">{row.diff.to}</span>
        </p>
      ) : (
        <p className="text-ink-strong">{row.content}</p>
      )}

      {row.due_move ? (
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <span className="numeric text-ink">
            {t('ijro.upload.move', {
              from: formatDate(row.due_move.from),
              to: formatDate(row.due_move.to),
            })}
          </span>
          <label className="inline-flex min-h-touch items-center gap-2">
            <input
              type="checkbox"
              className="size-5"
              checked={confirmed !== undefined}
              onChange={(event) =>
                setMove(event.target.checked ? (row.due_move?.suggested_kind ?? 'extension') : null)
              }
            />
            <span>{t('ijro.upload.confirmMove')}</span>
          </label>
          {confirmed !== undefined ? (
            <select
              aria-label={t('ijro.upload.moveKind')}
              className={FIELD}
              value={confirmed}
              onChange={(event) => setMove(event.target.value as ExtensionKind)}
            >
              <option value="extension">{t('ijro.card.due.kinds.extension')}</option>
              <option value="correction">{t('ijro.card.due.kinds.correction')}</option>
            </select>
          ) : null}
        </div>
      ) : null}

      {row.unmatched ? (
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <span className="text-ink-muted">
            {t('ijro.upload.unmatched', { raw: row.unmatched.raw })}
          </span>
          {row.unmatched.suggestions.length === 0 ? (
            <span className="text-ink-muted">{t('ijro.upload.noSuggestion')}</span>
          ) : (
            row.unmatched.suggestions.map((person) => (
              <Button
                key={person.id}
                size="small"
                look={alias === person.id ? 'primary' : 'plain'}
                aria-pressed={alias === person.id}
                onClick={() =>
                  onChoices({ ...choices, aliases: { ...choices.aliases, [row.id]: person.id } })
                }
              >
                {t('ijro.card.responsible.suggest', { name: person.name })}
              </Button>
            ))
          )}
        </div>
      ) : null}

      {row.class === 'vanished' ? (
        <label className="mt-1 inline-flex min-h-touch items-center gap-2">
          <input
            type="checkbox"
            className="size-5"
            checked={choices.removed.includes(row.id)}
            onChange={(event) =>
              onChoices({
                ...choices,
                removed: event.target.checked
                  ? [...choices.removed, row.id]
                  : choices.removed.filter((each) => each !== row.id),
              })
            }
          />
          <span>{t('ijro.upload.remove')}</span>
        </label>
      ) : null}
    </li>
  );
}
