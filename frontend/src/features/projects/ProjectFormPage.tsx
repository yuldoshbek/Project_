/**
 * Страницы создания и правки проекта (ORB-086).
 *
 * Страница отвечает за запросы и переходы, форма — за поля. Разделено потому, что форма
 * проверяется тестом без сети и без маршрутизатора: иначе каждая проверка поведения поля
 * начиналась бы с поднятия двух провайдеров.
 *
 * **После сохранения открывается карточка, а не список.** Это критерий приёмки, и он не
 * про удобство: список не отвечает на вопрос «сохранилось ли то, что я вводил». Человек,
 * которого вернули в список, открывает запись сам — и делает это после каждого
 * сохранения.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Navigate, useNavigate, useParams } from 'react-router-dom';

import { projectPath, ROUTES } from '../../app/routes';
import { useMayEdit } from '../../shared/mode/useMode';
import { ErrorState } from '../../shared/ui/ErrorState';
import { Skeleton } from '../../shared/ui/Skeleton';
import type { Project, ProjectDraft } from './api';
import { createProject, fetchDictionaries, fetchPeople, fetchProject, updateProject } from './api';
import { ProjectForm } from './ProjectForm';

export function NewProjectPage() {
  return <FormPage />;
}

export function EditProjectPage() {
  const { id } = useParams<'id'>();
  // Свойства нет вовсе, а не `id={undefined}`: при строгих необязательных свойствах это
  // разные вещи, и именно по нему страница различает создание и правку.
  return <FormPage {...(id === undefined ? {} : { id })} />;
}

function FormPage({ id }: { id?: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const mayEdit = useMayEdit();

  /**
   * Правка старой записи запрашивает и недействующие значения.
   *
   * Иначе направление или куратор, выведенные из обращения, исчезнут из списка, и форма
   * молча предложит сохранить проект без них — то есть правка названия стёрла бы
   * куратора. Форма создания, наоборот, недействующие не предлагает.
   */
  const editing = id !== undefined;

  const dictionaries = useQuery({
    queryKey: ['dictionaries', { includeInactive: editing }],
    queryFn: () => fetchDictionaries(editing),
    staleTime: 10 * 60_000,
  });

  const people = useQuery({
    queryKey: ['people', { includeInactive: editing }],
    queryFn: () => fetchPeople(editing),
    staleTime: 10 * 60_000,
  });

  const project = useQuery({
    queryKey: ['project', id],
    queryFn: () => fetchProject(id ?? ''),
    enabled: editing,
  });

  const save = useMutation({
    mutationFn: (draft: ProjectDraft) =>
      id === undefined ? createProject(draft) : updateProject(id, draft),
    onSuccess: async (saved: Project) => {
      // Список и карточка перечитываются, а не правятся на месте: цвет светофора и
      // процент считает сервер (ADR-0005), и подставить их здесь значило бы завести
      // второе место с тем же правилом.
      await queryClient.invalidateQueries({ queryKey: ['projects'] });
      queryClient.setQueryData(['project', saved.id], saved);
      void navigate(projectPath(saved.id), { replace: true });
    },
  });

  // Запись — дело помощника (ADR-0011). Руководителя сюда не приводит ни одна ссылка,
  // но адрес можно набрать руками, и отказ сервера на сохранении — худший способ об
  // этом узнать: к тому моменту форма уже заполнена. Переход объявлен разметкой, а не
  // вызовом в отрисовке: побочное действие при отрисовке React выполняет дважды.
  if (!mayEdit) {
    return <Navigate to={ROUTES.forbidden} replace />;
  }

  const pending = dictionaries.isPending || people.isPending || (editing && project.isPending);
  if (pending) return <Skeleton count={6} height={56} />;

  const failed = dictionaries.isError || people.isError || project.isError;
  if (failed || dictionaries.data === undefined || people.data === undefined) {
    return (
      <ErrorState
        onRetry={() => {
          void dictionaries.refetch();
          void people.refetch();
          if (editing) void project.refetch();
        }}
      />
    );
  }

  return (
    <section aria-label={editing ? t('projects.form.editLabel') : t('projects.form.createTitle')}>
      <ProjectForm
        {...(project.data === undefined ? {} : { project: project.data })}
        dictionaries={dictionaries.data}
        people={people.data}
        error={save.error}
        saving={save.isPending}
        onSubmit={(draft) => {
          save.mutate(draft);
        }}
        onCancel={() => {
          void navigate(editing && id !== undefined ? projectPath(id) : ROUTES.projects);
        }}
      />
    </section>
  );
}
