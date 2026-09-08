# SPEC — техническая спецификация ORBITA

Версия 2.0 · 08.09.2026 · Пересобрана после смены объёма ([COUNCIL-0002](council/COUNCIL-0002.md)):
система на двоих — помощник вносит данные, руководитель смотрит и анализирует.

Источник требований: [ТЗ v1.0](../tz/TZ-ORBITA-v1.0.md) ·
Контекст: [CONTEXT.md](CONTEXT.md) · Решения: [adr](adr)

Спецификация описывает **что должно быть построено**, с точностью, достаточной для
нарезки на тикеты. Реализационные детали, не влияющие на поведение, здесь не фиксируются.

---

## 1. Модель данных (схема `orbita`)

Общие поля всех таблиц: `id uuid pk default gen_random_uuid()`,
`created_at timestamptz not null default now()`, `updated_at timestamptz`.

### 1.1 Люди и доступ

**`users`** — `external_seta_id text unique null`, `email citext unique`, `full_name`,
`position`, `telegram_id bigint unique null` (обязателен для канала Telegram), `locale`
(`ru | uz-Cyrl | uz-Latn`), `timezone` (по умолчанию Asia/Tashkent), `is_active bool`,
`password_hash null` (пусто при провайдере SETA), `last_login_at`.

**`user_roles`** — `user_id fk`, `role` (`assistant | leader`), первичный ключ по паре.
Две роли, разграничения по проектам нет ([ADR-0011](adr/ADR-0011-two-user-scope.md)):
`assistant` — полный доступ, `leader` — чтение плюс решение по проекту в статусе
«На контроле руководителя».

Таблицы `project_members` нет и не будет: делить нечего. Если появится третий
пользователь с ограниченным доступом, возвращаться нужно к ADR-0003 — и до его
подключения, а не после.

**`people`** — сотрудники агентства: `full_name`, `position`, `department`,
`email null`, `phone null`, `is_active`. **Это не пользователи системы.** Куратор
проекта и исполнитель задачи — реальные люди, которые в ORBITA не входят: их
назначает помощник, чтобы знать, с кого спрашивать. Смешать их с `users` — значит
завести сорок учётных записей, которыми никто никогда не воспользуется, и получить
ложную картину: система будет выглядеть многопользовательской, не будучи такой.
Когда сотрудник получит доступ, у него появится запись в `users` со ссылкой на
`person_id` — справочник при этом не переделывается.

### 1.2 Справочники (ТЗ 7, редактируются администратором)

**`directions`** — `code`, `name_ru`, `name_uz_cyrl`, `name_uz_latn`, `sort_order`,
`is_active`. Стартовый набор из ТЗ 7: космический мониторинг, ДЗЗ, международное
сотрудничество, инфраструктура и техническое развитие, нормативно-регуляторная работа,
внутренние организационные инициативы.

**`priorities`** — `code` (`urgent | high | normal | low`), названия на трёх локалях,
`color`, `sort_order`, `escalation_enabled bool` (для `urgent` — да, ТЗ 7).

**`project_statuses`** — `code`
(`initiation | in_progress | on_hold | awaiting_decision | done | cancelled`),
названия, `is_terminal bool`, `requires_reason bool` (для `on_hold` и `cancelled` ТЗ
требует указания причины), `sort_order`.

**`settings`** — key-value с типизацией: `warn_days`, `warn_ratio`,
`escalation_delay_hours`, `escalation_step_hours`, `quiet_hours_start`, `quiet_hours_end`,
`max_upload_mb`, `allowed_mime`. Меняются в интерфейсе администратора без разработчика.

**`organizations`** — `name`, `short_name`, `country_code`, `kind`
(`ministry | agency | university | company | international`), `notes`.

### 1.3 Проекты

**`projects`** — `code` (человекочитаемый, вида PRJ-2026-001), `title`, `description`,
`kind` (`project | mini`), `classification` (`internal | restricted`) — граница проходит
по периметру системы: `restricted` не уходит ни в Google, ни в Telegram, ни в экспорт
([ADR-0007](adr/ADR-0007-restricted-data.md) в редакции ADR-0011),
`direction_id fk`, `curator_person_id fk people` (сотрудник агентства, не пользователь
системы), `status_code fk project_statuses`,
`status_reason text null`, `priority_code fk priorities`, `started_on date`,
`due_on date`, `finished_on date null`, `progress_pct smallint 0..100`,
`progress_mode` (`manual | auto`), `budget_note text null` (справочно, ТЗ 2.5 — без
интеграции с финансовыми системами), `template_id fk null`,
`archived_at timestamptz null`, `created_by fk`, `search_vector tsvector generated`.

`progress_pct` — ручной ввод куратора либо авторасчёт по доле выполненных задач; режим
выбирается полем `progress_mode`, по умолчанию `auto`.

**`project_partners`** — `project_id`, `organization_id`, `role text`.

**`milestones`** — `project_id fk`, `title`, `due_on date`, `status`
(`planned | done | missed`), `sort_order`, `description`.

**`project_templates`** — `name`, `kind`, `payload jsonb` (преднастроенные направление,
приоритет, набор вех, чек-листы). Стартовые шаблоны из ТЗ 6.1: международное
сотрудничество, программа мониторинга, внутренняя инициатива.

### 1.4 Задачи

**`tasks`** — `code` (вида TSK-2026-00123), `project_id fk null` (задача может
существовать вне проекта, ТЗ 1), `milestone_id fk null`, `title`, `description`,
`assignee_person_id fk people null` (кому поручено — сотрудник агентства),
`author_id fk users`, `status`
(`new | in_progress | in_review | done | cancelled`, ADR-0004), `priority_code fk`,
`due_at timestamptz null`, `started_at`, `completed_at`, `is_control bool` (поручение
руководителя, требующее контроля), `recurrence_rule text null` (RRULE),
`recurrence_parent_id fk self null`, `kanban_order numeric` (позиция в колонке),
`search_vector tsvector generated`.

Индексы: `(status, due_at)` — для просрочки, `(assignee_person_id, status)`,
`(project_id, status)`, GIN по `search_vector`.

**`task_checklist_items`** — `task_id`, `text`, `is_done`, `sort_order`.

**`tags`** и **`task_tags`** — `name` unique, связь многие-ко-многим.

Таблицы наблюдателей нет: пользователей двое, и оба видят всё.

### 1.5 Общение, файлы, календарь

**`comments`** — `entity_type` (`project | task`), `entity_id`, `author_id`, `body`,
`edited_at`, `deleted_at`. Упоминания вида «собака-имя» разбираются при сохранении и
порождают уведомление.

**`documents`** и **`document_versions`** — см. ADR-0009.

**`calendar_events`** — `title`, `kind` (`meeting`), `starts_at`, `ends_at`,
`is_all_day`, `location`, `project_id fk null`, `created_by`, `ics_uid`.

**`event_participants`** — `event_id`, `person_id fk people`, `response`
(`none | yes | no | maybe`). Участники встречи — сотрудники и внешние лица из
справочника, а не пользователи системы.

Единая лента календаря (ТЗ 6.3) — это **представление** поверх трёх источников: вехи
проектов, сроки задач, события-встречи. Отдельной таблицы «все события календаря» нет.

### 1.6 Уведомления, эскалация, аудит

**`notifications`** — ADR-0008. **`audit_log`** — ADR-0010 (нужен для отчётности и
восстановления хода событий, а не для контроля доступа).

Таблицы `escalations` нет: эскалировать некому (COUNCIL-0002). Нарушенный срок даёт
напоминание помощнику и строку в утренней сводке руководителю.

**`notification_preferences`** — `user_id`, `event_kind`, `channels text[]`.

**`project_health_snapshots`** — ежедневный снимок состояния проекта: `project_id`,
`taken_on date`, `health`, `status_code`, `progress_pct`, `overdue_tasks_count`,
`open_tasks_count`, `days_to_due`; уникальность по `(project_id, taken_on)`.
Отвечает на вопрос «где мы проседаем», на который светофор ответить не может: цвет
меняется от хода времени, и журнал изменений об этом не знает
([ADR-0014](adr/ADR-0014-progress-history.md)). Ретроспектива не восстанавливается —
задание должно работать до первого показа дашборда.

### 1.7 Интеграции

**`google_accounts`** — `user_id fk`, `google_sub`, `email`, `refresh_token_encrypted`,
`access_token_expires_at`, `orbita_calendar_id` (наш отдельный календарь),
`watched_calendar_ids text[]` (чьи встречи читаем), `sync_enabled bool default false`,
`last_sync_at`, `last_sync_error`. Токен обновления шифруется ключом из окружения;
ключ не входит в резервную копию базы ([ADR-0012](adr/ADR-0012-google-calendar-sync.md)).

**`calendar_sync_state`** — `account_id fk`, `calendar_id`, `sync_token`,
`updated_at`. При ответе `410 Gone` токен сбрасывается и идёт полная пересинхронизация.

**`calendar_links`** — связь нашей записи с событием Google: `entity_type`
(`milestone | task`), `entity_id`, `google_event_id`, `calendar_id`, `synced_at`.
Само событие в Google несёт `extendedProperties.private.orbita_entity` — иначе
выгруженная веха вернётся обратно «встречей» при следующем чтении.

**`external_events`** — встречи, прочитанные из Google: `account_id`, `google_event_id`,
`calendar_id`, `title`, `starts_at`, `ends_at`, `is_all_day`, `location`, `updated_at`,
`deleted_at`. Хранятся у нас, чтобы календарь работал при недоступности Google;
в Google не изменяются никогда.

Telegram отдельной таблицы не требует: получатель определяется по `users.telegram_id`,
факт отправки — записью в `notifications` ([ADR-0013](adr/ADR-0013-telegram-bot.md)).

### 1.8 Отчёты

**`report_definitions`** — `name`, `owner_id`, `filters jsonb`, `columns text[]`,
`format` (`docx | xlsx`), `schedule_rule null` (RRULE для автогенерации).

**`report_runs`** — `definition_id`, `generated_at`, `document_id fk`, `status`, `error`.

---

## 2. API (`/api/v1`)

Соглашения: JSON, поля в snake_case; списки — курсорная пагинация (`limit`, `cursor`);
ошибки в формате RFC 9457 (`type`, `title`, `status`, `detail`, `errors`). Фильтра
видимости нет: оба пользователя видят всё (ADR-0011). Роль проверяется на запись —
руководителю доступен только `POST /projects/{id}/decision`.

| Метод и путь | Назначение | Тикет |
|---|---|---|
| `POST /auth/login`, `/auth/refresh`, `/auth/logout` | Сессия | ORB-006 |
| `GET /me` | Профиль, роли, локаль, права | ORB-006 |
| `GET`, `POST /projects`; `GET`, `PATCH`, `DELETE /projects/{id}` | Проекты | ORB-011 |
| `POST /projects/{id}/archive`, `/restore` | Архив (ТЗ 6.1) | ORB-025 |
| `POST /projects/{id}/decision` | Решение руководителя по статусу «На контроле» | ORB-062 |
| `GET`, `POST /projects/{id}/milestones`; `PATCH`, `DELETE /milestones/{id}` | Вехи | ORB-012 |
| `GET`, `POST /tasks`; `GET`, `PATCH`, `DELETE /tasks/{id}` | Задачи | ORB-014 |
| `POST /tasks/bulk` | Массовые операции (ТЗ 6.2) | ORB-024 |
| `PATCH /tasks/{id}/position` | Перенос карточки на канбане | ORB-021 |
| `GET`, `POST /tasks/{id}/checklist`, `/tags` | Чек-лист и теги | ORB-015 |
| `GET`, `POST /comments`; `PATCH`, `DELETE /comments/{id}` | Комментарии | ORB-016 |
| `POST /documents`; `GET /documents/{id}/versions`, `/download` | Вложения | ORB-017 |
| `GET /calendar?from=&to=&kinds=` | Единая лента календаря | ORB-026 |
| `GET /calendar/feed/{token}.ics` | Выгрузка в .ics | ORB-028 |
| `GET /dashboard` | Все показатели одним ответом | ORB-029 |
| `GET /dashboard/gantt` | Данные диаграммы Ганта | ORB-031 |
| `GET /assistant/today` | Персональный вид помощника (U2) | ORB-032 |
| `GET /search?q=&types=` | Глобальный поиск | ORB-033 |
| `GET`, `POST /admin/directions`, `/priorities`, `/statuses`, `/settings` | Справочники | ORB-035 |
| `GET`, `POST /admin/users`; `PATCH /admin/users/{id}/roles` | Пользователи | ORB-045 |
| `GET /admin/audit` | Журнал аудита | ORB-045 |
| `GET`, `POST /reports/definitions`; `POST /reports/{id}/run`; `GET /reports/runs/{id}` | Отчёты | ORB-043 |
| `GET /notifications`; `POST /notifications/{id}/read` | Центр уведомлений | ORB-037 |
| `GET /briefing` | Экран «Доклад»: портфель, красная зона, ждёт решения, 7 дней вперёд | ORB-061 |
| `GET /dashboard/trend` | Динамика: что ухудшилось за неделю, что стоит на месте | ORB-064 |
| `GET /projects/{id}/history` | Полоса состояний проекта за период | ORB-064 |
| `GET /integrations/google/authorize`, `/callback` | Подключение календаря по OAuth | ORB-057 |
| `GET`, `PATCH /integrations/google` | Состояние синхронизации и выключатель | ORB-057 |
| `DELETE /integrations/google` | Отзыв доступа, удаление токена | ORB-057 |

---

## 3. Экраны (ТЗ 9)

| Экран | Ключевое требование | Тикет |
|---|---|---|
| Дашборд | Показатели, светофор, Гантт; наведение — детали, клик — переход в карточку (ТЗ 10.5) | ORB-030, ORB-031 |
| Список и канбан проектов | Фильтры по статусу, направлению, куратору | ORB-019 |
| Карточка проекта | Вехи, задачи, файлы, комментарии, история | ORB-018 |
| База задач | Три представления одних данных: таблица, канбан, календарь | ORB-020, ORB-021, ORB-027 |
| Карточка задачи | Чек-лист, комментарии, вложения, состояние эскалации | ORB-022 |
| Календарь | День, неделя, месяц; цвет по типу события и приоритету | ORB-027 |
| Отчёты | Конструктор: поля, период, фильтры; история запусков | ORB-043 |
| Мастер создания | Не более 3 шагов, цель — до 2 минут (ТЗ 10.5, 2.4) | ORB-023 |
| Вид помощника | «Что горит сегодня» по всему периметру руководителя | ORB-032 |
| **Доклад** | Экран для показа руководителю: портфель, красная зона, ждёт решения, 7 дней вперёд. Режим показа — крупно, без служебных элементов | ORB-061 |
| Настройки | Справочники, пороги, подключение Google, журнал изменений | ORB-035, ORB-045, ORB-057 |

## 4. Нефункциональные требования в проверяемых формулировках

| Требование ТЗ | Проверяемая формулировка | Тикет |
|---|---|---|
| 10.2 Производительность | Пользователей двое; p95 `GET /dashboard` и `GET /briefing` не более 400 мс на наборе 200 проектов и 3000 задач; p95 списков не более 250 мс. Медленный экран доклада ломает единственный сценарий, ради которого система существует | ORB-051 |
| 10.5 Скорость создания | Мастер: не более 3 экранов и 12 обязательных полей; сценарий U1 проходится за 120 секунд на UAT | ORB-023, ORB-052 |
| 10.1 Безопасность | TLS; заголовки безопасности; ограничение частоты входа; режим `restricted` покрыт тестами во всех точках выхода наружу (поиск, экспорт, Google, Telegram, .ics, почта); ни одного ключа в публичном репозитории и его истории | ORB-050 |
| 10.3 Локализация | Три локали полностью; ноль текстовых строк в компонентах; поиск находит одно и то же по трём написаниям | ORB-048, ORB-033 |
| 10.4 Надёжность | Ежедневная резервная копия БД и файлов; восстановление на чистом окружении не более 4 часов, прогон задокументирован | ORB-047 |
| 10.5 Адаптивность | Полная работа от 1024 px; просмотр и смена статуса от 360 px | ORB-049 |

## 5. Критерии приёмки системы (ТЗ 14)

1. Все требования раздела 6 ТЗ реализованы и проверены на данных агентства: не менее
   10 проектов и 50 задач (ORB-052).
2. Сценарии U1–U8 из ТЗ 8 проходятся вручную на UAT, каждый — с зафиксированным временем.
3. Разграничение доступа (U7) подтверждено автотестом и ручной проверкой.
4. Проверка службой безопасности пройдена без критических замечаний.
5. Резервное копирование и восстановление проверены на тестовом сценарии.
6. Внутренний регламент обязательного ведения проектов в системе утверждён (ТЗ 15).
