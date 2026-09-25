"""Реестр поручений вышестоящих органов «Ижро».

Пять таблиц по [ADR-0025](../../../../docs/adr/ADR-0025-ijro-standalone-register.md).
Поручение не сливается с проектом или задачей: у них разное происхождение (чужой
документ против нашей воли), разный владелец срока и разный вопрос от руководителя.
Связь есть только одна и только в одну сторону — задача помнит поручение, из которого
выросла (`tasks.ijro_assignment_id`, ТЗ 3.2). Состояние поручения из задач не выводится
(ТЗ 3.3).

Ленты хода исполнения здесь нет — она живёт в полиморфной таблице `comments`, где
поручение единственный владелец (`app.domain.comments`). Вложений у поручения пока нет
вовсе: файлы приходят в блоке 2 вместе с хранилищем и своей миграцией.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.ijro import (
    BAND_MAX_LENGTH,
    CODE_MAX_LENGTH,
    RESPONSIBLE_RAW_MAX_LENGTH,
    AliasSource,
    DocumentKind,
    DuePrecision,
    DueYearSource,
    IjroSource,
    IjroState,
    ImportState,
)
from app.repos.base import Base, Timestamps, UUIDPrimaryKey, Versioned
from app.repos.models.audit import Auditable


def _values(
    enum: type[
        IjroSource
        | DocumentKind
        | IjroState
        | DuePrecision
        | DueYearSource
        | ImportState
        | AliasSource
    ],
) -> str:
    """Список значений для `CHECK`, собранный из перечисления, а не переписанный руками.

    Переписанный руками список расходится с кодом молча: перечисление пополнили, а база
    продолжает отвергать новое значение — и ошибка приходит из привоза, а не из тестов.
    """
    return ", ".join(f"'{item.value}'" for item in enum)


class IjroDocument(Auditable, UUIDPrimaryKey, Timestamps, Base):
    """Документ вышестоящего органа: фармон, қарор, қонун, баён.

    Отдельная таблица, а не поле поручения, и цена ошибки видна на числах: **57
    документов на 164 поручения**. ПФ-155 встречается 32 раза, и в источнике он записан
    двумя способами — «Фармон ПФ-155-сон 14.10.2024 й» и «Фармон ПФ-155 14.10.2024».
    Номером в каждом поручении это были бы 32 копии, расходящиеся на первом же новом
    написании, а вопрос руководителя «что мы сделали по ПФ-155» получил бы ответ по
    23 строкам вместо 32.
    """

    __tablename__ = "ijro_documents"

    code_norm: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    """Нормализованный номер — ключ склейки написаний. Как нормализуется, решает ORB-102."""

    kind: Mapped[str] = mapped_column(String(20), nullable=False, default=DocumentKind.OTHER.value)
    number_raw: Mapped[str] = mapped_column(String(120), nullable=False)
    """Номер как в источнике. Сопоставление можно пересмотреть, потерянный исходник — нет."""

    issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    """Дата документа. Необязательна: в пяти ячейках из 165 её нет вовсе."""

    source: Mapped[str] = mapped_column(String(10), nullable=False)
    title_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Вся ячейка «Ҳужжат тури ва рақами» целиком, тремя абзацами как пришла."""

    __table_args__ = (
        CheckConstraint(f"kind IN ({_values(DocumentKind)})", name="kind_is_known"),
        CheckConstraint(f"source IN ({_values(IjroSource)})", name="source_is_known"),
        # «Какие документы от Кабинета Министров» — первый вопрос к реестру после «что горит».
        Index("ix_ijro_documents_source_issued_on", "source", "issued_on"),
    )


class IjroAssignment(Auditable, Versioned, UUIDPrimaryKey, Timestamps, Base):
    """Поручение — строка контрольной таблицы.

    Ключ повтора — `(документ, банд, срок)`. Проверено на всех 165 строках: **164 группы**,
    единственное слипание — строка, приведённая в источнике дважды байт в байт. Ключ без
    срока не годится: 23 пары `(документ, банд)` законно повторяются по месяцам — это
    регулярные поручения, и слить их значило бы потерять три срока из четырёх.
    """

    __tablename__ = "ijro_assignments"

    code: Mapped[str] = mapped_column(String(CODE_MAX_LENGTH), nullable=False, unique=True)

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ijro_documents.id", ondelete="RESTRICT"), nullable=False
    )
    """Не CASCADE: удаление документа не должно уносить историю исполнения его поручений."""

    band: Mapped[str | None] = mapped_column(String(BAND_MAX_LENGTH), nullable=True)
    """Пункт документа: «5.1-банд», «2-илова 26.3-банд», «9.а-банд».

    Пусто — **законное состояние**, а не ошибка разбора: одна строка из 165 пункта не
    имеет. Запрет `NOT NULL` выбросил бы её из реестра целиком.
    """

    band_sort: Mapped[str | None] = mapped_column(String(BAND_MAX_LENGTH), nullable=True)
    """Пункт, приведённый к виду, который сортируется по-человечески.

    Отдельное поле, потому что по самому банду сортировка врёт: «2.10» встаёт перед «2.9»,
    и карточка документа показывает пункты не по порядку. Как именно приводится — ORB-102.
    """

    content: Mapped[str] = mapped_column(Text, nullable=False)
    """Содержание поручения. В данных — в среднем 380–430 знаков, до полутора тысяч."""

    mechanism: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Подраздел «Амалга ошириш механизми» — как именно исполнять.

    Отдельным полем, а не в общем тексте: у ячейки есть внутренняя структура, и слив её в
    один абзац потерял бы то единственное, что говорит исполнителю, что делать.
    """

    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_raw: Mapped[str | None] = mapped_column(String(100), nullable=True)
    """Срок как в источнике: «25 декабрь», без года."""

    due_precision: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DuePrecision.EXACT.value
    )
    due_year_source: Mapped[str | None] = mapped_column(String(20), nullable=True)
    block_label: Mapped[str | None] = mapped_column(String(40), nullable=True)
    """Строка-разделитель, под которой строка стояла: «СЕНТЯБРЬ», «ДЕКАБРЬ».

    Хранится, чтобы перенесённую просрочку можно было увидеть глазами: месяц срока раньше
    месяца блока — это признак, а не ошибка.
    """

    responsible_raw: Mapped[str | None] = mapped_column(
        String(RESPONSIBLE_RAW_MAX_LENGTH), nullable=True
    )
    """Ответственный строкой источника. Хранится **всегда**, рядом с сопоставленным."""

    responsible_person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="SET NULL"), nullable=True
    )
    """Сотрудник агентства из справочника. Пусто, пока написание не сопоставлено человеком."""

    lead_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True
    )
    is_co_executor: Mapped[bool] = mapped_column(nullable=False, default=False)
    """Головной исполнитель — чужое ведомство, мы соисполнители. 55 строк из 165."""

    state: Mapped[str] = mapped_column(
        String(30), nullable=False, default=IjroState.NOT_STARTED.value
    )
    state_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    problem: Mapped[str | None] = mapped_column(Text, nullable=True)
    """«Муаммо» — что мешает исполнению."""

    proposal: Mapped[str | None] = mapped_column(Text, nullable=True)
    """«Таклиф» — что предлагаем сделать.

    Вместе с `problem` это и есть четвёртый документ заказчика, который сегодня пишут
    руками перед докладом. Пара полей на карточке превращает его в кнопку.
    """

    problem_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """Когда проблему трогали в последний раз: несвежая проблема хуже отсутствующей."""

    source_state_raw: Mapped[str | None] = mapped_column(String(400), nullable=True)
    """Графа «Ижро ҳолати» как пришла. Непуста в трёх строках из 165 — **Q34**."""

    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ijro_imports.id", ondelete="SET NULL"), nullable=True
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_in_import_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """Когда строку видели в выгрузке последний раз.

    Пропала — не удаляем: она могла исчезнуть и потому, что поручение закрыли, и потому,
    что у выгрузки поменялся фильтр. Удаление лишает возможности эти случаи различить.
    """

    __table_args__ = (
        # Ключ повтора. Проверен на всех 165 строках данных заказчика.
        #
        # NULLS NOT DISTINCT (PostgreSQL 15+) — обязательная часть ключа, а не тонкость.
        # По умолчанию два NULL считаются разными, и строка без пункта или без срока
        # (обе законны — см. `band` и `due_on`) проходила бы уникальность при каждом
        # привозе: еженедельная таблица задваивала бы ровно те строки, которые и так
        # труднее всего опознать глазами.
        UniqueConstraint("document_id", "band", "due_on", postgresql_nulls_not_distinct=True),
        CheckConstraint(f"state IN ({_values(IjroState)})", name="state_is_known"),
        CheckConstraint(
            f"due_precision IN ({_values(DuePrecision)})", name="due_precision_is_known"
        ),
        CheckConstraint(
            f"due_year_source IS NULL OR due_year_source IN ({_values(DueYearSource)})",
            name="due_year_source_is_known",
        ),
        # Признак без ведомства — это утверждение «главный кто-то другой» без ответа на
        # вопрос кто. Именно по этому ведомству собирается список «что сорвётся не по
        # нашей вине», и пустая ссылка сделала бы строку невидимой в нём.
        CheckConstraint(
            "is_co_executor IS FALSE OR lead_organization_id IS NOT NULL",
            name="co_executor_has_a_lead_organization",
        ),
        # «Что горит» — главный запрос к реестру, и он идёт по сроку среди незакрытых.
        Index("ix_ijro_assignments_state_due_on", "state", "due_on"),
        # «У кого сколько» — второй по частоте.
        Index(
            "ix_ijro_assignments_responsible_person_id_due_on", "responsible_person_id", "due_on"
        ),
    )


class IjroPersonAlias(UUIDPrimaryKey, Timestamps, Base):
    """Написание ответственного, сведённое с сотрудником.

    Таблица, а не алгоритм, — из-за одной строки в данных. Ответственных **29 написаний
    на ~21 человека**: `А. Арибжанов` / `А.Арибжонов` / `А.Арибжанов`, `Х. Рахмонов`
    кириллицей и `X. Рахмонов` латинской буквой. Свести их правилом заманчиво — пока не
    встретится `Ш. Арибжанов`: другой инициал, другой человек, и любое правило склейки по
    фамилии соединит его молча.

    Цена автоматической склейки — недостоверный показатель загрузки, по которому
    руководитель принимает решение. Цена ручного подтверждения — двадцать нажатий при
    первом привозе, и дальше система узнаёт написания сама.
    """

    __tablename__ = "ijro_person_aliases"

    alias_norm: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(10), nullable=False, default=AliasSource.AUTO.value)

    __table_args__ = (
        CheckConstraint(f"source IN ({_values(AliasSource)})", name="source_is_known"),
    )


class IjroOrgAlias(UUIDPrimaryKey, Timestamps, Base):
    """Написание ведомства, сведённое с организацией из справочника.

    То же, что с людьми, но мягче: ведомств меньше и пишутся они полнее. Отдельная таблица
    всё равно нужна — «Экология, атроф-муҳитни муҳофаза қилиш ва иқлим ўзгариши вазирлиги»
    в данных обрывается по-разному в зависимости от ширины ячейки.
    """

    __tablename__ = "ijro_org_aliases"

    alias_norm: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(10), nullable=False, default=AliasSource.AUTO.value)

    __table_args__ = (
        CheckConstraint(f"source IN ({_values(AliasSource)})", name="source_is_known"),
    )


class IjroImport(UUIDPrimaryKey, Timestamps, Base):
    """Партия привоза: один файл `.docx`, разобранный и, возможно, применённый.

    Отчёт о разборе живёт **в базе**, а не в памяти процесса. Предпросмотр — фаза, а не
    режим: помощник может уйти, вернуться и показать разбор руководителю, а применение
    остаётся идемпотентным без внешнего состояния.
    """

    __tablename__ = "ijro_imports"

    filename: Mapped[str] = mapped_column(String(400), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    """Тот же файл второй раз даёт «0 новых, 0 изменений», а не отказ.

    Не уникален по всей таблице: отвергнутый предпросмотр того же файла не должен мешать
    привезти его снова. Уникальность среди **применённых** держит частичный индекс ниже.
    """

    storage_key: Mapped[str | None] = mapped_column(String(400), nullable=True)
    """Исходник в объектном хранилище: без него разбор нельзя перепроверить."""

    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source: Mapped[str | None] = mapped_column(String(10), nullable=True)
    table_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    """Год таблицы из её заголовка: в сроках года нет, и взять его больше неоткуда."""

    rows_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_changed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_unrecognized: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ImportState.PREVIEW.value
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    report: Mapped[dict[str, object] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    """Построчный разбор: что новое, что изменилось, что не легло и по какой причине.

    Причины — кодами (`header-mismatch`, `due-unparsed`, `band-missing`), а не свободным
    текстом: по кодам видно, какая форма встречается часто и стоит ли учить разбор.
    """

    __table_args__ = (
        CheckConstraint(f"state IN ({_values(ImportState)})", name="state_is_known"),
        CheckConstraint(
            f"source IS NULL OR source IN ({_values(IjroSource)})", name="source_is_known"
        ),
        # Один и тот же файл применяется один раз. Среди отвергнутых предпросмотров
        # повторы законны: человек посмотрел и передумал.
        Index(
            "uq_ijro_imports_sha256_applied",
            "sha256",
            unique=True,
            postgresql_where="state = 'applied'",
        ),
    )
