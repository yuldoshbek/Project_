/**
 * Правка карточки проекта — вымышленная запись до утверждения экрана.
 *
 * Цикл блока — «экран → утверждение → API» (CLAUDE.md). Чтение идёт из настоящего API, а
 * правка организаций и сведений пока ложится сюда, в память вкладки, и накладывается
 * поверх ответа сервера: экран можно потрогать на настоящих данных, ничего не записав в
 * базу. Перезагрузка страницы правку сбрасывает — экран говорит об этом прямо.
 *
 * API под утверждённый экран:
 *
 * - `PUT /api/v1/projects/{id}/details` — название, ответственный, направление, регион,
 *   описание, с версией проекта;
 * - `PUT /api/v1/projects/{id}/organizations/{organization_id}` — добавить организацию
 *   или сменить её роль;
 * - `DELETE /api/v1/projects/{id}/organizations/{organization_id}`;
 * - `POST /api/v1/organizations` — новая организация: название и вид.
 *
 * Когда API появится, модуль удаляется, а мутации в `useProjects.ts` идут в `request()`.
 */

import type {
  NewOrganization,
  OrganizationRef,
  OrganizationRole,
  ProjectCard,
  ProjectDetail,
  ProjectDetails,
  Ref,
} from './model';

type Membership = ProjectDetail['organizations'][number];

interface Overlay {
  details?: {
    title: string;
    responsible: Ref | null;
    direction: string | null;
    region: string | null;
    description: string | null;
  };
  organizations?: Membership[];
}

const overlays = new Map<string, Overlay>();
const created: OrganizationRef[] = [];
let sequence = 0;

/** Роль Центра и «головное ведомство чужое» — то же правило, что у сервера. */
function derived(organizations: Membership[]) {
  return {
    center_role: organizations.find((org) => org.is_center)?.role ?? null,
    lead_outside: organizations.some((org) => !org.is_center && org.role === 'lead_agency'),
  };
}

export function withDraftCard(card: ProjectCard): ProjectCard {
  const overlay = overlays.get(card.id);
  if (!overlay) return card;
  return {
    ...card,
    ...(overlay.details
      ? { title: overlay.details.title, responsible: overlay.details.responsible }
      : {}),
    ...(overlay.organizations ? derived(overlay.organizations) : {}),
  };
}

export function withDraft(detail: ProjectDetail): ProjectDetail {
  const overlay = overlays.get(detail.id);
  if (!overlay) return detail;
  return {
    ...detail,
    ...withDraftCard(detail),
    ...(overlay.details ?? {}),
    ...(overlay.organizations ? { organizations: overlay.organizations } : {}),
  };
}

export function withCreated(list: OrganizationRef[]): OrganizationRef[] {
  return [...list, ...created];
}

function organizationsOf(project: ProjectDetail): Membership[] {
  return overlays.get(project.id)?.organizations ?? project.organizations;
}

function update(id: string, patch: Overlay) {
  overlays.set(id, { ...overlays.get(id), ...patch });
}

export const draft = {
  saveDetails(
    project: ProjectDetail,
    input: ProjectDetails,
    names: { responsible: Ref | null; direction: string | null; region: string | null },
  ) {
    update(project.id, {
      details: {
        title: input.title.trim(),
        responsible: names.responsible,
        direction: names.direction,
        region: names.region,
        description: input.description?.trim() || null,
      },
    });
  },

  setOrganization(project: ProjectDetail, organization: OrganizationRef, role: OrganizationRole) {
    const rest = organizationsOf(project).filter((org) => org.id !== organization.id);
    const next: Membership = {
      id: organization.id,
      name: organization.short_name ?? organization.name,
      role,
      is_center: organization.is_founded_by_agency,
    };
    // Центр — первым, как в ответе сервера: ради него срез и заводился.
    const organizations = next.is_center ? [next, ...rest] : [...rest, next];
    update(project.id, { organizations });
  },

  removeOrganization(project: ProjectDetail, organizationId: string) {
    update(project.id, {
      organizations: organizationsOf(project).filter((org) => org.id !== organizationId),
    });
  },

  createOrganization(input: NewOrganization): OrganizationRef {
    sequence += 1;
    const organization: OrganizationRef = {
      id: `draft-org-${sequence}`,
      name: input.name.trim(),
      short_name: null,
      kind: input.kind,
      is_founded_by_agency: false,
    };
    created.push(organization);
    return organization;
  },

  /** Для тестов: начать с чистого листа. */
  reset() {
    overlays.clear();
    created.length = 0;
    sequence = 0;
  },
};
