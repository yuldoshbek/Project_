"""Справочники (ТЗ 3.9).

Хранят то, что принадлежит данным: название на трёх письменностях, порядок, цвет,
видимость. Смысл значений принадлежит коду — см. `app.domain.dictionaries`.

Названия лежат тремя отдельными столбцами, а не строкой с переводами в JSON: по ним
сортируют и ищут, а сортировка по полю JSON в PostgreSQL не пользуется индексом.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.dictionaries import OrganizationKind
from app.repos.base import Base, Timestamps, UUIDPrimaryKey
from app.repos.models.audit import Auditable

ORGANIZATION_KINDS = ", ".join(f"'{kind.value}'" for kind in OrganizationKind)


class LocalizedName:
    """Название на трёх письменностях.

    Все три обязательны. Необязательный перевод означает, что в узбекской версии
    интерфейса рано или поздно появится русское слово, и заметят это на приёмке.
    """

    name_ru: Mapped[str] = mapped_column(String(200), nullable=False)
    name_uz_cyrl: Mapped[str] = mapped_column(String(200), nullable=False)
    name_uz_latn: Mapped[str] = mapped_column(String(200), nullable=False)


class DictionaryEntry(UUIDPrimaryKey, LocalizedName, Timestamps):
    """Общее у всех справочников.

    `code` — стабильный технический ключ, на него ссылается код и внешние ключи; он не
    меняется никогда. `is_active` — мягкое исключение: удалять значение, на которое уже
    ссылаются записи, нельзя, а убрать его из форм создания нужно, иначе в старом проекте
    исчезнет направление, по которому его когда-то завели.
    """

    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Direction(DictionaryEntry, Base):
    """Направление работы агентства. Необязательное поле проекта (ТЗ 3.1)."""

    __tablename__ = "directions"


class Region(DictionaryEntry, Base):
    """Регион — одна из 14 административных единиц (ТЗ 3.1).

    Двенадцать областей, Республика Каракалпакстан и город Ташкент. Необязательное поле
    проекта. Заведён справочником, а не списком в коде, потому что
    вопрос «нужен ли руководителю срез по регионам» ещё открыт (V7): если нужен — срез
    собирается по этой таблице, если нет — поле остаётся пустым и никому не мешает.
    """

    __tablename__ = "regions"


class ProjectTypeRef(DictionaryEntry, Base):
    """Тип проекта — десять значений из ТЗ 3.9, каждое со своим шаблоном вех.

    Смысл типа коду не нужен: он не считает по нему ни одного сигнала. Тип приносит
    шаблон вех, и это всё — поэтому здесь нет перечисления рядом, в отличие от статусов.
    Заказчик вправе завести одиннадцатый тип из интерфейса, и система от этого не
    изменится.
    """

    __tablename__ = "project_types"


class ProjectTypeMilestone(UUIDPrimaryKey, LocalizedName, Timestamps, Base):
    """Веха шаблона: что подставляется в новый проект этого типа (ТЗ 3.1).

    Ради этого типы и заводятся. Помощник выбирает «нормативный акт» — и получает
    разработку, согласование, внесение в Кабмин готовыми строками, а не вспоминает их
    каждый раз. Дальше вехи правятся как обычные: шаблон — это начало, а не рамка.

    `offset_days` — через сколько дней от начала проекта наступает срок вехи. Дни, а не
    доли срока: «согласование через месяц» — это то, что помощник знает, а «согласование
    на 40 % срока» — то, что ему пришлось бы вычислять.

    **Место в шаблоне уникально** — пара «тип + порядок». Две вехи на одном месте не
    имеют порядка между собой, и новый проект получал бы их то так, то этак. Эта же пара —
    ключ, по которому наполнение (`app.seed`) узнаёт уже заведённую веху. Цена названа
    вслух: переставить две вехи местами одним `UPDATE` нельзя, перестановка идёт через
    временное значение порядка в одной транзакции.
    """

    __tablename__ = "project_type_milestones"

    project_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_types.id", ondelete="CASCADE"), nullable=False
    )
    offset_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("offset_days >= 0", name="offset_is_not_negative"),
        UniqueConstraint("project_type_id", "sort_order"),
    )


class TaskTypeRef(DictionaryEntry, Base):
    """Тип задачи — одиннадцать значений из ТЗ 3.9.

    Как и у проекта, смысл принадлежит данным: тип отвечает на вопрос «что это за
    работа», а не меняет поведение системы.
    """

    __tablename__ = "task_types"


class ProjectStatusRef(DictionaryEntry, Base):
    """Статусы проекта. Суффикс `Ref` отличает таблицу от перечисления, где живёт смысл."""

    __tablename__ = "project_statuses"

    is_terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_reason: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="grey")


class TaskStatusRef(DictionaryEntry, Base):
    """Статусы задачи. «Просрочена» здесь отсутствует: она вычисляется (инвариант 1)."""

    __tablename__ = "task_statuses"

    is_terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="grey")


class Organization(Auditable, UUIDPrimaryKey, Timestamps, Base):
    """Организация: министерство, ведомство, хокимият, международная организация, компания.

    `is_founded_by_agency` отмечает Центр космического мониторинга — организацию,
    учреждённую агентством (CONTEXT, «Учреждённая организация»). Признак, а не вид,
    потому что Центр — это компания и одновременно наша: на нём держится срез «что держит
    Центр» (ТЗ 5), а вид отвечает на другой вопрос.

    Журналируется: смена вида или названия — деловое изменение, и вопрос «кто это
    поменял» по ней возникает.

    **Название уникально**, и это ключ, а не только поиск. Технического кода у
    организации нет и не заводится: ТЗ 3.4 его не называет, а помощник знает организацию
    по названию. Две строки с одним названием — это одна организация, заведённая дважды:
    роли в проектах и написания из таблиц «Ижро» разошлись бы по двум записям, и срез «что
    держит Центр» потерял бы половину. Тот же ключ узнаёт Центр при повторном наполнении
    (`app.seed`).
    """

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    is_founded_by_agency: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint(f"kind IN ({ORGANIZATION_KINDS})", name="kind_is_known"),
        CheckConstraint(
            "country_code IS NULL OR country_code = upper(country_code)",
            name="country_code_upper",
        ),
    )


class Setting(UUIDPrimaryKey, Timestamps, Base):
    """Пороги сигналов: их меняет помощник, а не разработчик (ТЗ 3.9).

    Не путать с переменными окружения: те задаёт тот, кто разворачивает систему.

    `min_value` и `max_value` нужны форме редактирования: порог «горит за 900 дней»
    выключает сигнал, не сообщая об этом, и восстановить его будет некому.
    """

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    value_type: Mapped[str] = mapped_column(String(20), nullable=False)
    description_ru: Mapped[str] = mapped_column(Text, nullable=False)
    min_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
