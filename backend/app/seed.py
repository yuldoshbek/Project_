"""Наполнение справочников под ТЗ v2.0, раздел 3.9.

Запуск: `make seed` (или `python -m app.seed`).

**Существующие записи не изменяются.** Справочники редактирует помощник, а не код (ТЗ 3.9):
он вправе переименовать статус, поменять порядок или поправить шаблон вех. Повторный
запуск наполнения, затирающий его правки, превратил бы редактируемый справочник в
декорацию. Поэтому каждая вставка — `ON CONFLICT DO NOTHING` по естественному ключу
записи, и команда безопасна после каждого обновления системы.

Откуда значения:

- типы проектов и типы задач — дословно из ТЗ 3.9;
- шаблоны вех — ТЗ их не перечисляет; здесь минимальные шаблоны, допущение записано в
  [открытых вопросах](../../docs/OPEN-QUESTIONS.md) (V11);
- регионы — 14 административных единиц из ТЗ 3.1: двенадцать областей, Республика
  Каракалпакстан и город Ташкент;
- статусы — ТЗ 3.1 и 3.2, коды — из `app.domain.dictionaries`;
- пороги — значения по умолчанию из ТЗ 4 и 8;
- Центр космического мониторинга — учреждённая агентством организация (ТЗ 1, 3.4): на
  нём держится срез «что держит Центр».

Сотрудники агентства (`people`) сюда не входят: это реальные люди, и вносит их помощник.
Выдуманные записи пришлось бы вычищать перед эксплуатацией, а часть наверняка осталась бы.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, cast

import structlog
from sqlalchemy import CursorResult
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dictionaries import OrganizationKind, ProjectStatus, SettingKey, TaskStatus
from app.domain.people import Role
from app.observability import configure_logging
from app.repos.database import dispose_database, init_database, session_scope
from app.repos.models import (
    Direction,
    Organization,
    ProjectStatusRef,
    ProjectTypeMilestone,
    ProjectTypeRef,
    Region,
    Setting,
    TaskStatusRef,
    TaskTypeRef,
    User,
)
from app.settings import get_settings

logger = structlog.get_logger(__name__)

Row = dict[str, Any]


def named(code: str, ru: str, uz_cyrl: str, uz_latn: str, sort_order: int, **extra: Any) -> Row:
    """Строка справочника с названием на трёх письменностях.

    Все три обязательны: незаполненный перевод — это русское слово в узбекском
    интерфейсе, и заметят его на приёмке, а не здесь.
    """
    return {
        "code": code,
        "name_ru": ru,
        "name_uz_cyrl": uz_cyrl,
        "name_uz_latn": uz_latn,
        "sort_order": sort_order,
        **extra,
    }


def step(ru: str, uz_cyrl: str, uz_latn: str, offset_days: int) -> Row:
    """Веха шаблона: название и через сколько дней от начала проекта наступает её срок."""
    return {
        "name_ru": ru,
        "name_uz_cyrl": uz_cyrl,
        "name_uz_latn": uz_latn,
        "offset_days": offset_days,
    }


# --------------------------------------------------------------------------
# Типы проектов и их шаблоны вех (ТЗ 3.9)
# --------------------------------------------------------------------------

PROJECT_TYPES: list[Row] = [
    named("monitoring_cycle", "Цикл мониторинга", "Мониторинг цикли", "Monitoring sikli", 10),
    named(
        "regulation",
        "Нормативный акт",
        "Норматив-ҳуқуқий ҳужжат",
        "Normativ-huquqiy hujjat",
        20,
    ),
    named("standard", "Стандарт", "Стандарт", "Standart", 30),
    named("platform", "Платформа или ИТ", "Платформа ёки АТ", "Platforma yoki AT", 40),
    named(
        "satellite_mission",
        "Спутниковая миссия",
        "Сунъий йўлдош миссияси",
        "Sunʼiy yoʻldosh missiyasi",
        50,
    ),
    named(
        "industry_pilot",
        "Пилот с отраслью",
        "Тармоқ билан пилот лойиҳа",
        "Tarmoq bilan pilot loyiha",
        60,
    ),
    named("service_order", "Заказ услуги", "Хизмат буюртмаси", "Xizmat buyurtmasi", 70),
    named(
        "international",
        "Международное сотрудничество",
        "Халқаро ҳамкорлик",
        "Xalqaro hamkorlik",
        80,
    ),
    named("staff_education", "Кадры и образование", "Кадрлар ва таълим", "Kadrlar va taʼlim", 90),
    named(
        "higher_authority_order",
        "Заказ вышестоящего органа",
        "Юқори турувчи орган буюртмаси",
        "Yuqori turuvchi organ buyurtmasi",
        100,
    ),
]

# Шаблоны — начало, а не рамка: вехи подставляются в новый проект и дальше правятся как
# обычные (ТЗ 3.1). Сроки в днях от начала проекта — ориентир, который помощник поправит
# под конкретную работу; сами шаблоны правятся в «Управлении» (допущение V11).
MILESTONE_TEMPLATES: dict[str, list[Row]] = {
    "monitoring_cycle": [
        step(
            "Получение космических снимков", "Космик суратларни олиш", "Kosmik suratlarni olish", 30
        ),
        step(
            "Обработка и анализ данных",
            "Маълумотларга ишлов бериш ва таҳлил",
            "Maʼlumotlarga ishlov berish va tahlil",
            60,
        ),
        step(
            "Отчёт по результатам мониторинга",
            "Мониторинг натижалари бўйича ҳисобот",
            "Monitoring natijalari boʻyicha hisobot",
            90,
        ),
    ],
    # Единственный шаблон, чьи вехи названы в документах проекта: «разработка,
    # согласование, внесение в Кабмин» (CONTEXT, «Веха»).
    "regulation": [
        step(
            "Разработка проекта акта",
            "Ҳужжат лойиҳасини ишлаб чиқиш",
            "Hujjat loyihasini ishlab chiqish",
            30,
        ),
        step(
            "Согласование с министерствами и ведомствами",
            "Вазирлик ва идоралар билан келишиш",
            "Vazirlik va idoralar bilan kelishish",
            60,
        ),
        step(
            "Внесение в Кабинет Министров",
            "Вазирлар Маҳкамасига киритиш",
            "Vazirlar Mahkamasiga kiritish",
            90,
        ),
        step("Принятие", "Қабул қилиниши", "Qabul qilinishi", 120),
    ],
    "standard": [
        step(
            "Разработка проекта стандарта",
            "Стандарт лойиҳасини ишлаб чиқиш",
            "Standart loyihasini ishlab chiqish",
            60,
        ),
        step("Обсуждение и согласование", "Муҳокама ва келишиш", "Muhokama va kelishish", 120),
        step(
            "Утверждение и регистрация",
            "Тасдиқлаш ва рўйхатдан ўтказиш",
            "Tasdiqlash va roʻyxatdan oʻtkazish",
            180,
        ),
    ],
    "platform": [
        step("Техническое задание", "Техник топшириқ", "Texnik topshiriq", 30),
        step("Разработка", "Ишлаб чиқиш", "Ishlab chiqish", 120),
        step(
            "Опытная эксплуатация",
            "Синов тариқасида фойдаланиш",
            "Sinov tariqasida foydalanish",
            150,
        ),
        step("Ввод в эксплуатацию", "Фойдаланишга топшириш", "Foydalanishga topshirish", 180),
    ],
    "satellite_mission": [
        step(
            "Концепция и техническое задание",
            "Концепция ва техник топшириқ",
            "Konsepsiya va texnik topshiriq",
            90,
        ),
        step(
            "Договор с изготовителем",
            "Ишлаб чиқарувчи билан шартнома",
            "Ishlab chiqaruvchi bilan shartnoma",
            180,
        ),
        step("Запуск", "Учириш", "Uchirish", 720),
        step("Ввод в эксплуатацию", "Фойдаланишга топшириш", "Foydalanishga topshirish", 810),
    ],
    "industry_pilot": [
        step("Соглашение с отраслью", "Тармоқ билан келишув", "Tarmoq bilan kelishuv", 30),
        step("Проведение пилота", "Пилот лойиҳани ўтказиш", "Pilot loyihani oʻtkazish", 120),
        step(
            "Отчёт и предложения по масштабированию",
            "Ҳисобот ва кенгайтириш бўйича таклифлар",
            "Hisobot va kengaytirish boʻyicha takliflar",
            150,
        ),
    ],
    "service_order": [
        step(
            "Заявка и техническое задание",
            "Буюртманома ва техник топшириқ",
            "Buyurtmanoma va texnik topshiriq",
            14,
        ),
        step("Договор", "Шартнома", "Shartnoma", 30),
        step("Оказание услуги", "Хизмат кўрсатиш", "Xizmat koʻrsatish", 75),
        step(
            "Акт приёмки",
            "Қабул қилиш далолатномаси",
            "Qabul qilish dalolatnomasi",
            90,
        ),
    ],
    "international": [
        step(
            "Переговоры и проект документа",
            "Музокаралар ва ҳужжат лойиҳаси",
            "Muzokaralar va hujjat loyihasi",
            60,
        ),
        step(
            "Внутригосударственное согласование",
            "Давлат ичида келишиш",
            "Davlat ichida kelishish",
            120,
        ),
        step("Подписание", "Имзолаш", "Imzolash", 150),
    ],
    "staff_education": [
        step(
            "Программа и отбор участников",
            "Дастур ва иштирокчиларни танлаш",
            "Dastur va ishtirokchilarni tanlash",
            30,
        ),
        step("Обучение", "Ўқитиш", "Oʻqitish", 120),
        step("Итоги и отчёт", "Якунлар ва ҳисобот", "Yakunlar va hisobot", 150),
    ],
    "higher_authority_order": [
        step("План исполнения", "Ижро режаси", "Ijro rejasi", 7),
        step("Исполнение", "Ижро", "Ijro", 45),
        step(
            "Доклад об исполнении",
            "Ижро тўғрисида ахборот",
            "Ijro toʻgʻrisida axborot",
            60,
        ),
    ],
}

# --------------------------------------------------------------------------
# Типы задач (ТЗ 3.9)
# --------------------------------------------------------------------------

TASK_TYPES: list[Row] = [
    named("technical_spec", "Техническое задание", "Техник топшириқ", "Texnik topshiriq", 10),
    named(
        "review_and_endorse",
        "Рассмотрение и визирование",
        "Кўриб чиқиш ва визалаш",
        "Koʻrib chiqish va vizalash",
        20,
    ),
    named("approval", "Согласование", "Келишиш", "Kelishish", 30),
    named(
        "cabinet_submission",
        "Внесение в Кабмин",
        "Вазирлар Маҳкамасига киритиш",
        "Vazirlar Mahkamasiga kiritish",
        40,
    ),
    named(
        "analytical_note",
        "Аналитическая информация",
        "Таҳлилий маълумот",
        "Tahliliy maʼlumot",
        50,
    ),
    named("site_visit", "Выезд на место", "Жойига чиқиш", "Joyiga chiqish", 60),
    named(
        "request_or_survey",
        "Запрос или опросник",
        "Сўров ёки сўровнома",
        "Soʻrov yoki soʻrovnoma",
        70,
    ),
    named(
        "subplatform_upload",
        "Выгрузка в субплатформу",
        "Субплатформага юклаш",
        "Subplatformaga yuklash",
        80,
    ),
    named(
        "participant_selection",
        "Отбор участников",
        "Иштирокчиларни танлаш",
        "Ishtirokchilarni tanlash",
        90,
    ),
    named(
        "ijro_report",
        "Подготовка сведений по Ижро",
        "Ижро бўйича маълумот тайёрлаш",
        "Ijro boʻyicha maʼlumot tayyorlash",
        100,
    ),
    named("other", "Прочее", "Бошқа", "Boshqa", 110),
]

# --------------------------------------------------------------------------
# Направления и регионы (ТЗ 3.1)
# --------------------------------------------------------------------------

# Направления работы агентства — стартовый набор из мандата агентства. Поле проекта
# необязательное (ТЗ 3.1), набор правится помощником.
DIRECTIONS: list[Row] = [
    named(
        "space_monitoring", "Космический мониторинг", "Космик мониторинг", "Kosmik monitoring", 10
    ),
    named(
        "remote_sensing",
        "Дистанционное зондирование Земли",
        "Ерни масофадан зондлаш",
        "Yerni masofadan zondlash",
        20,
    ),
    named(
        "international",
        "Международное сотрудничество",
        "Халқаро ҳамкорлик",
        "Xalqaro hamkorlik",
        30,
    ),
    named(
        "infrastructure",
        "Инфраструктура и техническое развитие",
        "Инфратузилма ва техник ривожланиш",
        "Infratuzilma va texnik rivojlanish",
        40,
    ),
    named(
        "regulatory",
        "Нормативно-регуляторная работа",
        "Меъёрий-тартибга солиш ишлари",
        "Meʼyoriy-tartibga solish ishlari",
        50,
    ),
    named(
        "internal",
        "Внутренние организационные инициативы",
        "Ички ташкилий ташаббуслар",
        "Ichki tashkiliy tashabbuslar",
        60,
    ),
]

# Порядок — принятый в государственной статистике: Каракалпакстан, области по алфавиту,
# город Ташкент последним.
REGIONS: list[Row] = [
    named(
        "karakalpakstan",
        "Республика Каракалпакстан",
        "Қорақалпоғистон Республикаси",
        "Qoraqalpogʻiston Respublikasi",
        10,
    ),
    named("andijan", "Андижанская область", "Андижон вилояти", "Andijon viloyati", 20),
    named("bukhara", "Бухарская область", "Бухоро вилояти", "Buxoro viloyati", 30),
    named("jizzakh", "Джизакская область", "Жиззах вилояти", "Jizzax viloyati", 40),
    named(
        "kashkadarya", "Кашкадарьинская область", "Қашқадарё вилояти", "Qashqadaryo viloyati", 50
    ),
    named("navoi", "Навоийская область", "Навоий вилояти", "Navoiy viloyati", 60),
    named("namangan", "Наманганская область", "Наманган вилояти", "Namangan viloyati", 70),
    named("samarkand", "Самаркандская область", "Самарқанд вилояти", "Samarqand viloyati", 80),
    named(
        "surkhandarya", "Сурхандарьинская область", "Сурхондарё вилояти", "Surxondaryo viloyati", 90
    ),
    named("syrdarya", "Сырдарьинская область", "Сирдарё вилояти", "Sirdaryo viloyati", 100),
    named("tashkent_region", "Ташкентская область", "Тошкент вилояти", "Toshkent viloyati", 110),
    named("fergana", "Ферганская область", "Фарғона вилояти", "Fargʻona viloyati", 120),
    named("khorezm", "Хорезмская область", "Хоразм вилояти", "Xorazm viloyati", 130),
    named("tashkent_city", "город Ташкент", "Тошкент шаҳри", "Toshkent shahri", 140),
]

# --------------------------------------------------------------------------
# Статусы (ТЗ 3.1, 3.2)
# --------------------------------------------------------------------------

# Флаги `is_terminal` и `requires_reason` берутся из домена, а не пишутся руками: смысл
# статуса принадлежит коду (`app.domain.dictionaries`), и расхождение здесь означало бы
# справочник, который говорит одно, а расчёт делает другое.
PROJECT_STATUS_NAMES: list[tuple[ProjectStatus, str, str, str, str]] = [
    (ProjectStatus.IN_PROGRESS, "В работе", "Ишда", "Ishda", "blue"),
    (ProjectStatus.ON_HOLD, "На паузе", "Тўхтатилган", "Toʻxtatilgan", "amber"),
    (ProjectStatus.DONE, "Завершён", "Якунланган", "Yakunlangan", "green"),
    (ProjectStatus.CANCELLED, "Отменён", "Бекор қилинган", "Bekor qilingan", "grey"),
]

PROJECT_STATUSES: list[Row] = [
    named(
        status.value,
        ru,
        uz_cyrl,
        uz_latn,
        (index + 1) * 10,
        color=color,
        is_terminal=status.is_terminal,
        requires_reason=status.requires_reason,
    )
    for index, (status, ru, uz_cyrl, uz_latn, color) in enumerate(PROJECT_STATUS_NAMES)
]

# «Просрочена» здесь отсутствует намеренно: это вычисляемый признак, а не состояние
# работы (CLAUDE.md, инвариант о просрочке).
TASK_STATUS_NAMES: list[tuple[TaskStatus, str, str, str, str]] = [
    (TaskStatus.NEW, "Новая", "Янги", "Yangi", "grey"),
    (TaskStatus.IN_PROGRESS, "В работе", "Ишда", "Ishda", "blue"),
    (TaskStatus.IN_REVIEW, "На проверке", "Текширувда", "Tekshiruvda", "violet"),
    (TaskStatus.DONE, "Готова", "Бажарилган", "Bajarilgan", "green"),
    (TaskStatus.CANCELLED, "Отменена", "Бекор қилинган", "Bekor qilingan", "grey"),
]

TASK_STATUSES: list[Row] = [
    named(
        status.value,
        ru,
        uz_cyrl,
        uz_latn,
        (index + 1) * 10,
        color=color,
        is_terminal=status.is_terminal,
    )
    for index, (status, ru, uz_cyrl, uz_latn, color) in enumerate(TASK_STATUS_NAMES)
]

# --------------------------------------------------------------------------
# Пороги сигналов (ТЗ 4, 8)
# --------------------------------------------------------------------------

# Границы нужны форме редактирования: порог «горит за 900 дней» выключает сигнал, не
# сообщая об этом, и восстановить его будет некому.
SETTINGS: list[Row] = [
    {
        "key": SettingKey.BURN_DAYS.value,
        "value": 7,
        "value_type": "days",
        "min_value": 1,
        "max_value": 60,
        "description_ru": "За сколько дней до срока незакрытая работа считается горящей (ТЗ 4)",
    },
    {
        "key": SettingKey.QUIET_DAYS.value,
        "value": 14,
        "value_type": "days",
        "min_value": 1,
        "max_value": 180,
        "description_ru": "Сколько дней без движения считается молчанием (ТЗ 4)",
    },
    {
        "key": SettingKey.IMPEDIMENT_STALE_DAYS.value,
        "value": 14,
        "value_type": "days",
        "min_value": 1,
        "max_value": 180,
        "description_ru": (
            "Через сколько дней строка «что мешает» перестаёт считаться действующей: "
            "запись месячной давности говорит не о препятствии, а о том, что её забыли "
            "обновить"
        ),
    },
    {
        "key": SettingKey.MIN_CLOSED_FOR_PACE.value,
        "value": 10,
        "value_type": "count",
        "min_value": 1,
        "max_value": 100,
        "description_ru": (
            "Сколько закрытых задач нужно, чтобы отвечать на «успеваем?»; при меньшем "
            "числе — «мало данных» (ТЗ 4)"
        ),
    },
    {
        "key": SettingKey.SUMMARY_AT.value,
        "value": "08:30",
        "value_type": "time",
        "description_ru": "Время утренней сводки руководителю по Ташкенту (ТЗ 8)",
    },
]

# --------------------------------------------------------------------------
# Пользователи и организации
# --------------------------------------------------------------------------

# Два пользователя (ТЗ 1.1), по одному на роль. Ни почты, ни пароля: вход — личная
# ссылка (ADR-0029), первую выпускает `python -m app.access_cli`. Имена — должности, а не
# ФИО: выдумывать имена сотрудников государственного органа нельзя, настоящее помощник
# впишет сам.
USERS: list[Row] = [
    {
        "role": Role.ASSISTANT.value,
        "full_name": "Помощник заместителя директора",
        "locale": "ru",
    },
    {
        "role": Role.LEADER.value,
        "full_name": "Заместитель директора",
        "locale": "ru",
    },
]

CENTER_NAME = "Центр космического мониторинга и геоинформационных технологий (МЧЖ)"

# Одна организация, а не справочник ведомств: Центр учреждён агентством, и срез «что
# держит Центр» (ТЗ 5) без него не собрать. Остальные организации помощник вносит по
# реальным партнёрам — выдуманный список министерств пришлось бы вычищать.
ORGANIZATIONS: list[Row] = [
    {
        "name": CENTER_NAME,
        "short_name": "Центр космического мониторинга",
        "kind": OrganizationKind.COMPANY.value,
        "is_founded_by_agency": True,
    },
]


async def _insert_missing(
    session: AsyncSession, model: type[Any], rows: list[Row], key: str | list[str]
) -> int:
    """Добавляет отсутствующие строки, не трогая существующие.

    `ON CONFLICT DO NOTHING` — не оптимизация, а требование: правки помощника в
    справочниках должны переживать обновление системы.

    Строки вставляются по одной, а не пачкой: у них разный набор полей (у одних есть
    `requires_reason`, у других нет), и групповая вставка потребовала бы приводить их к
    общему виду, подставляя значения по умолчанию руками — мимо тех, что объявлены в
    модели.
    """
    keys = [key] if isinstance(key, str) else key
    added = 0
    for row in rows:
        statement = insert(model).values(**row).on_conflict_do_nothing(index_elements=keys)
        result = cast("CursorResult[Any]", await session.execute(statement))
        added += result.rowcount or 0
    return added


async def _seed_project_types(session: AsyncSession) -> tuple[int, int]:
    """Типы проектов и шаблоны вех. Возвращает число добавленных типов и вех.

    **Шаблон заводится только вместе с новым типом.** Тип, который уже есть в базе,
    принадлежит помощнику целиком, включая шаблон: если он убрал из «нормативного акта»
    лишнюю веху, повторное наполнение не должно вернуть её обратно. `ON CONFLICT` по
    паре «тип + порядок» здесь страховка на случай гонки, а не основной механизм.
    """
    types_added = 0
    milestones_added = 0
    for row in PROJECT_TYPES:
        statement = (
            insert(ProjectTypeRef)
            .values(**row)
            .on_conflict_do_nothing(index_elements=["code"])
            .returning(ProjectTypeRef.id)
        )
        created: uuid.UUID | None = await session.scalar(statement)
        if created is None:
            continue

        types_added += 1
        template = [
            {**milestone, "project_type_id": created, "sort_order": (index + 1) * 10}
            for index, milestone in enumerate(MILESTONE_TEMPLATES.get(row["code"], []))
        ]
        milestones_added += await _insert_missing(
            session, ProjectTypeMilestone, template, ["project_type_id", "sort_order"]
        )
    return types_added, milestones_added


async def seed(session: AsyncSession) -> dict[str, int]:
    """Наполняет справочники. Возвращает число добавленных записей по каждому."""
    types_added, milestones_added = await _seed_project_types(session)
    added = {
        "project_types": types_added,
        "project_type_milestones": milestones_added,
        "task_types": await _insert_missing(session, TaskTypeRef, TASK_TYPES, "code"),
        "directions": await _insert_missing(session, Direction, DIRECTIONS, "code"),
        "regions": await _insert_missing(session, Region, REGIONS, "code"),
        "project_statuses": await _insert_missing(
            session, ProjectStatusRef, PROJECT_STATUSES, "code"
        ),
        "task_statuses": await _insert_missing(session, TaskStatusRef, TASK_STATUSES, "code"),
        "settings": await _insert_missing(session, Setting, SETTINGS, "key"),
        "users": await _insert_missing(session, User, USERS, "role"),
        "organizations": await _insert_missing(session, Organization, ORGANIZATIONS, "name"),
    }
    await session.flush()
    return added


async def _run() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.use_json_logs)
    init_database(settings)
    try:
        async for session in session_scope():
            added = await seed(session)
    finally:
        await dispose_database()

    if any(added.values()):
        logger.info("seed_completed", added=added)
    else:
        logger.info("seed_completed", added=added, note="всё уже на месте")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
