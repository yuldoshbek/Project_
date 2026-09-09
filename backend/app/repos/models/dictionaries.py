"""Справочники.

Хранят то, что принадлежит данным: название на трёх письменностях, порядок, цвет,
видимость. Смысл значений принадлежит коду — см. `app.domain.dictionaries`.

Названия лежат тремя отдельными столбцами, а не строкой с переводами в JSON: по ним
сортируют и ищут, а сортировка по полю JSON в PostgreSQL не пользуется индексом.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.repos.base import Base, Timestamps, UUIDPrimaryKey


class LocalizedName:
    """Название на трёх письменностях (ТЗ 10.3).

    Все три обязательны. Необязательный перевод означает, что в узбекской версии
    интерфейса рано или поздно появится русское слово, и заметят это на приёмке.
    """

    name_ru: Mapped[str] = mapped_column(String(200), nullable=False)
    name_uz_cyrl: Mapped[str] = mapped_column(String(200), nullable=False)
    name_uz_latn: Mapped[str] = mapped_column(String(200), nullable=False)


class DictionaryEntry(UUIDPrimaryKey, LocalizedName, Timestamps):
    """Общее для всех справочников.

    `code` — стабильный технический ключ, на него ссылается код и внешние ключи; он не
    меняется никогда. `is_active` — мягкое исключение: удалять значение, на которое уже
    ссылаются записи, нельзя, а убрать его из форм создания нужно (критерий ORB-010).
    """

    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Direction(DictionaryEntry, Base):
    """Направление работы (ТЗ 7).

    Стартовый набор взят из мандата агентства (ТЗ 3.1): космический мониторинг, ДЗЗ,
    международное сотрудничество и далее. Справочник редактируемый — портфель агентства
    меняется вместе с задачами, которые на него возлагают.
    """

    __tablename__ = "directions"


class ProjectStatusRef(DictionaryEntry, Base):
    """Статус проекта (ТЗ 7).

    Суффикс `Ref` отличает таблицу от перечисления `ProjectStatus`, в котором живёт смысл.
    """

    __tablename__ = "project_statuses"

    is_terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_reason: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="grey")


class TaskStatusRef(DictionaryEntry, Base):
    """Статус задачи.

    «Просрочена» здесь отсутствует: это вычисляемый признак, а не состояние работы
    (ADR-0004). Попытка завести её значением справочника вернула бы ровно ту проблему,
    ради ухода от которой принималось решение.
    """

    __tablename__ = "task_statuses"

    is_terminal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    color: Mapped[str] = mapped_column(String(20), nullable=False, default="grey")


class PriorityRef(DictionaryEntry, Base):
    """Приоритет (ТЗ 7)."""

    __tablename__ = "priorities"

    color: Mapped[str] = mapped_column(String(20), nullable=False, default="grey")

    warn_days_override: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    """Свой порог жёлтой зоны для этого приоритета.

    Нужен «Срочно»: по ADR-0005 у него порог равен нулю — задача жёлтая с момента
    постановки и красная сразу после срока. Хранится значением, а не условием в коде,
    чтобы помощник мог поправить его сам.
    """


class Organization(UUIDPrimaryKey, Timestamps, Base):
    """Организация-партнёр (ТЗ 6.1, сценарий U6).

    Не наследует `DictionaryEntry`: у организации нет технического кода и нет трёх
    названий — она называется так, как называется, включая зарубежных партнёров с
    латинским написанием.
    """

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(300), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint(
            "country_code IS NULL OR country_code = upper(country_code)",
            name="country_code_upper",
        ),
    )


class Setting(UUIDPrimaryKey, Timestamps, Base):
    """Настраиваемый параметр системы.

    Не путать с `app.settings`: там настройки окружения — адреса, ключи, пароли, которые
    задаёт тот, кто разворачивает систему. Здесь то, что меняет помощник в интерфейсе:
    пороги светофора, интервалы напоминаний, время сводки.

    Значение хранится в JSONB, потому что параметры разнотипны: число дней, доля,
    время суток, список интервалов. Отдельная колонка на каждый тип превратила бы таблицу
    в набор почти всегда пустых полей.
    """

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    description_ru: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(String(20), nullable=False)
    min_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
