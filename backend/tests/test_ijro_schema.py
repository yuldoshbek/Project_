"""Схема реестра «Ижро»: ограничения держит база, а не добрая воля кода (ORB-101).

Проверяется не «создаются ли таблицы» — это видно и так, — а четыре обещания, каждое из
которых выведено из настоящих данных заказчика и каждое из которых дороже всего нарушить
молча.

Первое: **ключ повтора работает**. `(документ, банд, срок)` даёт 164 группы на 165 строк;
если база его не держит, еженедельный привоз задвоит реестр, и заметят это через месяц.

Второе: **пустой пункт — законное состояние**. Одна строка из 165 банда не имеет, и запрет
на пустое значение выбросил бы её целиком.

Третье: **соисполнительство без ведомства запрещено**. Признак «главный кто-то другой» без
ответа на вопрос кто делает строку невидимой в списке «что сорвётся не по нашей вине» — а
это главный вопрос руководителя к реестру.

Четвёртое: **поручение стало владельцем ленты и вложений**. Своей ленты реестр не заводит,
и если `CHECK` о нём не знает, первая же реплика о ходе исполнения не запишется.

Все проверки идут через `flush`, а не через `add`: ограничение срабатывает на записи, и
тест, который её не доводит до базы, проверяет только собственные ожидания.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.comments import CommentTarget
from app.domain.dictionaries import OrganizationKind
from app.domain.documents import DocumentTarget
from app.domain.ijro import DuePrecision, IjroSource, IjroState
from app.repos.models import Comment, IjroAssignment, IjroDocument, IjroImport, Organization

pytestmark = pytest.mark.infra


async def a_document(session: AsyncSession, *, code: str = "PF-155") -> IjroDocument:
    document = IjroDocument(
        code_norm=f"{code}-{uuid.uuid4().hex[:8]}",
        kind="farmon",
        number_raw=code,
        issued_on=date(2024, 10, 14),
        source=IjroSource.LEGAL.value,
    )
    session.add(document)
    await session.flush()
    return document


async def an_assignment(
    session: AsyncSession,
    document: IjroDocument,
    *,
    band: str | None = "5.1-банд",
    due_on: date | None = date(2026, 12, 25),
    **extra: object,
) -> IjroAssignment:
    assignment = IjroAssignment(
        code=f"IJR-2026-{uuid.uuid4().hex[:6]}",
        document_id=document.id,
        band=band,
        due_on=due_on,
        content="Топшириқ мазмуни",
        **extra,
    )
    session.add(assignment)
    await session.flush()
    return assignment


class TestTheRepeatKey:
    """Ключ повтора — единственное, что отличает еженедельный привоз от задвоения."""

    async def test_the_same_document_band_and_due_date_cannot_repeat(
        self, session: AsyncSession
    ) -> None:
        document = await a_document(session)
        await an_assignment(session, document)

        with pytest.raises(IntegrityError):
            await an_assignment(session, document)

    async def test_the_same_band_with_another_due_date_is_allowed(
        self, session: AsyncSession
    ) -> None:
        """Регулярные поручения — 23 пары в данных: один пункт, четыре срока за год.

        Слить их значило бы потерять три срока из четырёх, и именно поэтому срок входит
        в ключ.
        """
        document = await a_document(session)
        await an_assignment(session, document, due_on=date(2026, 9, 30))
        await an_assignment(session, document, due_on=date(2026, 10, 30))

        found = list(await session.scalars(select(IjroAssignment.id)))
        assert len(found) == 2

    async def test_an_assignment_without_a_band_is_legal(self, session: AsyncSession) -> None:
        """Одна строка из 165 пункта не имеет. Запрет выбросил бы её из реестра."""
        document = await a_document(session)
        assignment = await an_assignment(session, document, band=None)

        assert assignment.band is None


class TestOneDocumentIsOneRow:
    """57 документов на 164 поручения: склейка написаний держится этой уникальностью."""

    async def test_the_same_normalised_number_cannot_be_written_twice(
        self, session: AsyncSession
    ) -> None:
        """ПФ-155 записан в источнике двумя способами и встречается 32 раза.

        Если нормализованный номер перестанет быть уникальным, «Фармон ПФ-155-сон» и
        «Фармон ПФ-155» заведут два документа, и карточка расколется надвое: 23 поручения
        в одной, 9 в другой. Вопрос «что мы сделали по ПФ-155» получит половину ответа и
        не подаст виду.
        """
        code = f"PF-155-{uuid.uuid4().hex[:8]}"
        session.add(
            IjroDocument(
                code_norm=code, kind="farmon", number_raw="ПФ-155-сон", source=IjroSource.LEGAL
            )
        )
        await session.flush()

        with pytest.raises(IntegrityError):
            session.add(
                IjroDocument(
                    code_norm=code, kind="farmon", number_raw="ПФ-155", source=IjroSource.LEGAL
                )
            )
            await session.flush()


class TestCoExecution:
    """«Асосий ижрочи» — 55 строк из 165, и по ним собирается список «что сорвётся»."""

    async def test_the_flag_demands_a_lead_organization(self, session: AsyncSession) -> None:
        document = await a_document(session)

        with pytest.raises((IntegrityError, DBAPIError)):
            await an_assignment(session, document, is_co_executor=True)

    async def test_the_flag_with_an_organization_is_accepted(self, session: AsyncSession) -> None:
        document = await a_document(session)
        ministry = Organization(name="Сув хўжалиги вазирлиги", kind=OrganizationKind.MINISTRY.value)
        session.add(ministry)
        await session.flush()

        assignment = await an_assignment(
            session, document, is_co_executor=True, lead_organization_id=ministry.id
        )

        assert assignment.lead_organization_id == ministry.id


class TestDefaults:
    async def test_a_new_assignment_is_not_started_with_an_exact_due_date(
        self, session: AsyncSession
    ) -> None:
        """Умолчания названы явно: «не начато» и «срок точный».

        Точность по умолчанию именно `exact`, а не «до конца года»: приписать сроку
        неточность, которой источник не заявлял, значит перестать показывать горящее.
        """
        document = await a_document(session)
        assignment = await an_assignment(session, document)

        assert assignment.state == IjroState.NOT_STARTED.value
        assert assignment.due_precision == DuePrecision.EXACT.value

    async def test_an_unknown_state_is_refused_by_the_database(self, session: AsyncSession) -> None:
        """Словарь состояний держит база, а не проверка в сервисе.

        Сервис можно обойти привозом, сидом или консолью; ограничение обойти нельзя.
        """
        document = await a_document(session)

        with pytest.raises((IntegrityError, DBAPIError)):
            await an_assignment(session, document, state="просрочено")


class TestTheAssignmentOwnsATimelineAndFiles:
    """Своей ленты реестр не заводит — он становится владельцем существующей."""

    async def test_a_note_about_progress_can_be_written(self, session: AsyncSession) -> None:
        document = await a_document(session)
        assignment = await an_assignment(session, document)

        session.add(
            Comment(
                entity_type=CommentTarget.IJRO_ASSIGNMENT.value,
                entity_id=assignment.id,
                body="Материал отправлен в Ҳисоб палатаси",
            )
        )
        await session.flush()

        written = await session.scalar(select(Comment).where(Comment.entity_id == assignment.id))
        assert written is not None

    async def test_an_unknown_owner_is_still_refused(self, session: AsyncSession) -> None:
        """Проверка не превратилась в «разрешено всё»: третье значение добавлено, а не снято."""
        with pytest.raises((IntegrityError, DBAPIError)):
            session.add(Comment(entity_type="meeting", entity_id=uuid.uuid4(), body="встреча"))
            await session.flush()

    def test_files_know_the_new_owner_too(self) -> None:
        assert DocumentTarget.IJRO_ASSIGNMENT.value == "ijro_assignment"


class TestImportBatches:
    async def test_the_same_file_can_be_previewed_twice_before_it_is_applied(
        self, session: AsyncSession
    ) -> None:
        """Отвергнутый предпросмотр не должен мешать привезти тот же файл снова.

        Уникальность держится только среди применённых партий — частичным индексом.
        Человек посмотрел разбор, передумал, вернулся: это обычный ход работы, а не ошибка.
        """
        digest = uuid.uuid4().hex
        for _ in range(2):
            session.add(IjroImport(filename="назорат.docx", sha256=digest))
        await session.flush()

        found = list(await session.scalars(select(IjroImport.id)))
        assert len(found) == 2

    async def test_the_same_file_cannot_be_applied_twice(self, session: AsyncSession) -> None:
        digest = uuid.uuid4().hex
        now = datetime.now(UTC)
        session.add(
            IjroImport(filename="назорат.docx", sha256=digest, state="applied", applied_at=now)
        )
        await session.flush()

        with pytest.raises(IntegrityError):
            session.add(
                IjroImport(filename="назорат.docx", sha256=digest, state="applied", applied_at=now)
            )
            await session.flush()
