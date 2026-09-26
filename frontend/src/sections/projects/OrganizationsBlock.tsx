/**
 * Организации проекта и их роли (ТЗ 3.1) — основа двух срезов: «что держит Центр» (ТЗ 5)
 * и «зависит от чужих» (ТЗ 4: головное ведомство не агентство и не Центр).
 *
 * Стоимость ввода решает, будут ли роли заполнены вообще (ТЗ 1): роль Центра — одно
 * касание, чужая организация — поиск по справочнику и роль, новой организации достаточно
 * названия и вида. Роль меняется на месте, без отдельной формы.
 *
 * Головное ведомство у проекта одно: вторая строка с этой ролью сделала бы непонятным, из-за
 * кого проект «зависит от чужих», — выбор этой роли для второй организации закрыт.
 */

import { Building2, Plus, X } from 'lucide-react';
import { useId, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { describeError } from '@/shared/api/client';
import { cn } from '@/shared/lib/cn';
import { Button } from '@/shared/ui/Button';
import { Failure } from '@/shared/ui/States';

import { Block } from './Block';
import type { OrganizationKind, OrganizationRef, OrganizationRole, ProjectDetail } from './model';
import {
  useCreateOrganization,
  useOrganizations,
  useRemoveOrganization,
  useSetOrganization,
} from './useProjects';

const ROLES: readonly OrganizationRole[] = ['customer', 'executor', 'co_executor', 'lead_agency'];

/** Роли Центра для касания: головным ведомством Центр не бывает — он не ведомство. */
const CENTER_ROLES: readonly OrganizationRole[] = ['executor', 'co_executor', 'customer'];

const KINDS: readonly OrganizationKind[] = [
  'ministry',
  'agency',
  'khokimiyat',
  'international',
  'company',
];

/** Сколько совпадений показать под поиском: больше на телефоне не просматривают. */
const MATCHES = 6;

const SELECT =
  'min-h-touch rounded-[var(--radius)] border border-line-strong bg-card px-2 text-sm text-ink';

type Membership = ProjectDetail['organizations'][number];

function normalized(value: string): string {
  return value.trim().toLocaleLowerCase('ru');
}

interface OrganizationsBlockProps {
  project: ProjectDetail;
  canEdit: boolean;
}

export function OrganizationsBlock({ project, canEdit }: OrganizationsBlockProps) {
  const { t } = useTranslation();
  const catalog = useOrganizations(canEdit);
  const setOrganization = useSetOrganization();
  const remove = useRemoveOrganization();
  const create = useCreateOrganization();
  const [adding, setAdding] = useState(false);

  const options = catalog.data ?? [];
  const center = options.find((org) => org.is_founded_by_agency);
  const hasCenter = project.organizations.some((org) => org.is_center);
  const lead = project.organizations.find((org) => org.role === 'lead_agency');
  const busy = setOrganization.isPending || remove.isPending || create.isPending;
  const failed = [setOrganization, remove, create].find((mutation) => mutation.isError);

  /** Строка проекта → запись справочника: роль меняется у той же организации. */
  const refOf = (member: Membership): OrganizationRef =>
    options.find((org) => org.id === member.id) ?? {
      id: member.id,
      name: member.name,
      short_name: null,
      kind: 'agency',
      is_founded_by_agency: member.is_center,
    };

  const assign = (organization: OrganizationRef, role: OrganizationRole) =>
    setOrganization.mutate({ project, organization, role });

  return (
    <Block title={t('projects.orgs.title')} question={t('projects.orgs.question')}>
      {project.organizations.length === 0 ? (
        <p className="text-sm text-ink-muted">{t('projects.orgs.none')}</p>
      ) : (
        <ul className="flex flex-col divide-y divide-line">
          {project.organizations.map((member) => (
            <li key={member.id} className="flex flex-wrap items-center gap-2 py-2">
              {/* На телефоне название — отдельной строкой: рядом с выбором роли длинное
                  «Центр космического мониторинга» налезало на него. */}
              <span className="flex min-w-0 flex-1 basis-full items-center gap-2 sm:basis-auto">
                {member.is_center ? (
                  <span className="inline-flex shrink-0 items-center gap-1 rounded-[var(--radius-pill)] bg-accent-soft px-2 py-0.5 text-xs text-accent-ink">
                    <Building2 className="size-3" aria-hidden="true" />
                    {t('projects.orgs.center')}
                  </span>
                ) : null}
                <span
                  className={cn(
                    'min-w-0 text-sm',
                    member.is_center ? 'font-medium text-ink-strong' : 'text-ink',
                  )}
                >
                  {member.name}
                </span>
              </span>
              {canEdit ? (
                <span className="ml-auto flex items-center gap-1">
                  <select
                    aria-label={t('projects.orgs.roleOf', { name: member.name })}
                    value={member.role}
                    disabled={busy}
                    onChange={(event) =>
                      assign(refOf(member), event.target.value as OrganizationRole)
                    }
                    className={SELECT}
                  >
                    {ROLES.map((role) => (
                      <option
                        key={role}
                        value={role}
                        disabled={
                          role === 'lead_agency' &&
                          (member.is_center || (lead !== undefined && lead.id !== member.id))
                        }
                      >
                        {t(`projects.roles.${role}`)}
                      </option>
                    ))}
                  </select>
                  <Button
                    look="quiet"
                    size="icon"
                    disabled={busy}
                    aria-label={t('projects.orgs.remove', { name: member.name })}
                    onClick={() => remove.mutate({ project, organizationId: member.id })}
                  >
                    <X className="size-4" aria-hidden="true" />
                  </Button>
                </span>
              ) : (
                <span className="text-sm text-ink-muted">{t(`projects.roles.${member.role}`)}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      {project.lead_outside ? (
        <p className="mt-2 rounded-[var(--radius-sm)] bg-wait-soft px-2 py-1 text-xs text-wait-ink">
          {t('projects.orgs.outsideHint')}
        </p>
      ) : null}

      {canEdit && center && !hasCenter ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="text-sm text-ink">{t('projects.orgs.centerQuick')}</span>
          {CENTER_ROLES.map((role) => (
            <Button key={role} size="small" disabled={busy} onClick={() => assign(center, role)}>
              {t(`projects.roles.${role}`)}
            </Button>
          ))}
        </div>
      ) : null}

      {canEdit ? (
        adding ? (
          <AddOrganization
            project={project}
            options={options}
            leadTaken={lead !== undefined}
            busy={busy}
            onAdd={(organization, role) =>
              setOrganization.mutate(
                { project, organization, role },
                { onSuccess: () => setAdding(false) },
              )
            }
            onCreate={(input, role) =>
              create.mutate(input, {
                onSuccess: (organization) =>
                  setOrganization.mutate(
                    { project, organization, role },
                    { onSuccess: () => setAdding(false) },
                  ),
              })
            }
            onCancel={() => setAdding(false)}
          />
        ) : (
          <Button
            look="plain"
            size="small"
            className="mt-3"
            onClick={() => {
              setOrganization.reset();
              create.reset();
              setAdding(true);
            }}
          >
            <Plus className="size-4" aria-hidden="true" />
            {t('projects.orgs.add')}
          </Button>
        )
      ) : null}

      {failed?.error ? (
        <div className="mt-3">
          <Failure detail={describeError(failed.error)} />
        </div>
      ) : null}

      {canEdit ? (
        <p className="mt-3 text-xs text-ink-muted">{t('projects.orgs.draftNote')}</p>
      ) : null}
    </Block>
  );
}

interface AddOrganizationProps {
  project: ProjectDetail;
  options: OrganizationRef[];
  leadTaken: boolean;
  busy: boolean;
  onAdd: (organization: OrganizationRef, role: OrganizationRole) => void;
  onCreate: (input: { name: string; kind: OrganizationKind }, role: OrganizationRole) => void;
  onCancel: () => void;
}

function AddOrganization({
  project,
  options,
  leadTaken,
  busy,
  onAdd,
  onCreate,
  onCancel,
}: AddOrganizationProps) {
  const { t } = useTranslation();
  const ids = useId();
  const [query, setQuery] = useState('');
  const [chosen, setChosen] = useState<OrganizationRef | null>(null);
  const [creating, setCreating] = useState(false);
  const [kind, setKind] = useState<OrganizationKind>('ministry');
  const [role, setRole] = useState<OrganizationRole>('customer');

  const present = new Set(project.organizations.map((org) => org.id));
  const needle = normalized(query);
  const available = options.filter((org) => !present.has(org.id));
  const matches = available
    .filter(
      (org) =>
        !needle ||
        normalized(org.name).includes(needle) ||
        normalized(org.short_name ?? '').includes(needle),
    )
    .slice(0, MATCHES);
  const exact = options.some(
    (org) => normalized(org.name) === needle || normalized(org.short_name ?? '') === needle,
  );

  const ready = (chosen !== null || (creating && needle !== '')) && !busy;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    if (chosen) onAdd(chosen, role);
    else onCreate({ name: query.trim(), kind }, role);
  };

  return (
    <form
      onSubmit={submit}
      className="mt-3 flex flex-col gap-3 rounded-[var(--radius)] border border-line bg-sunken p-3"
    >
      <label htmlFor={`${ids}-search`} className="text-sm text-ink">
        {t('projects.orgs.search')}
      </label>
      <input
        id={`${ids}-search`}
        value={query}
        autoFocus
        onChange={(event) => {
          setQuery(event.target.value);
          setChosen(null);
          setCreating(false);
        }}
        placeholder={t('projects.orgs.pick')}
        className="min-h-touch w-full rounded-[var(--radius)] border border-line-strong bg-card px-2 text-[15px] text-ink"
      />

      {!chosen && !creating ? (
        <div className="flex flex-col gap-1">
          {matches.map((org) => (
            <button
              key={org.id}
              type="button"
              onClick={() => {
                setChosen(org);
                setQuery(org.short_name ?? org.name);
                if (org.is_founded_by_agency) setRole('executor');
              }}
              className="flex min-h-touch items-center justify-between gap-3 rounded-[var(--radius)] px-2 text-left text-sm text-ink hover:bg-hover"
            >
              <span className="min-w-0">{org.short_name ?? org.name}</span>
              <span className="shrink-0 text-xs text-ink-muted">
                {org.is_founded_by_agency
                  ? t('projects.orgs.center')
                  : t(`projects.orgs.kinds.${org.kind}`)}
              </span>
            </button>
          ))}
          {needle && !exact ? (
            <button
              type="button"
              onClick={() => setCreating(true)}
              className="flex min-h-touch items-center gap-2 rounded-[var(--radius)] px-2 text-left text-sm font-medium text-accent-ink hover:bg-hover"
            >
              <Plus className="size-4 shrink-0" aria-hidden="true" />
              {t('projects.orgs.create', { name: query.trim() })}
            </button>
          ) : null}
        </div>
      ) : null}

      {creating ? (
        <div className="flex flex-col gap-1">
          <label htmlFor={`${ids}-kind`} className="text-sm text-ink">
            {t('projects.orgs.kind')}
          </label>
          <select
            id={`${ids}-kind`}
            value={kind}
            onChange={(event) => setKind(event.target.value as OrganizationKind)}
            className={SELECT}
          >
            {KINDS.map((each) => (
              <option key={each} value={each}>
                {t(`projects.orgs.kinds.${each}`)}
              </option>
            ))}
          </select>
        </div>
      ) : null}

      {chosen || creating ? (
        <div className="flex flex-col gap-1">
          <label htmlFor={`${ids}-role`} className="text-sm text-ink">
            {t('projects.orgs.role')}
          </label>
          <select
            id={`${ids}-role`}
            value={role}
            onChange={(event) => setRole(event.target.value as OrganizationRole)}
            className={SELECT}
          >
            {ROLES.map((each) => (
              <option
                key={each}
                value={each}
                disabled={
                  each === 'lead_agency' && (leadTaken || chosen?.is_founded_by_agency === true)
                }
              >
                {t(`projects.roles.${each}`)}
              </option>
            ))}
          </select>
          {leadTaken ? (
            <span className="text-xs text-ink-muted">{t('projects.orgs.leadTaken')}</span>
          ) : null}
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button type="submit" look="primary" disabled={!ready}>
          {creating ? t('projects.orgs.createSubmit') : t('projects.orgs.submit')}
        </Button>
        <Button type="button" look="quiet" onClick={onCancel}>
          {t('projects.orgs.cancel')}
        </Button>
      </div>
    </form>
  );
}
