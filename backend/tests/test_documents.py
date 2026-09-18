"""Вложения и версии (ORB-017).

Пять критериев карточки, и у каждого своё место, где он ломается тихо.

**Версия вместо второго документа** ломается тем, что второй файл с тем же именем заводит
вторую карточку. Список тогда выглядит рабочим — в нём просто два одинаковых имени, — и
беда обнаруживается через месяц, когда правку внесли в одну «Смету», а открывают другую.

**Дедупликация по содержимому** ломается противоположным образом: сравнением по имени и
размеру вместо отпечатка. Такое сравнение проходит все очевидные проверки и не проходит
ни одной настоящей — два разных документа одинакового размера встречаются постоянно.

**Ссылка из хранилища** ломается тем, что файл начинают отдавать через приложение: с
виду то же самое, а по сути — обработчик, занятый на всё время передачи. Проверяется не
наличие адреса в ответе, а то, что содержимое за ним лежит в хранилище и что срок жизни
ссылки конечен.

**Отказ по размеру и типу** ломается невнятностью: «недопустимый файл» заставляет
угадывать. Проверяется текст — в нём обязаны быть и предел, и то, что прислали.

**Предпросмотр** ломается тем, что состояние остаётся «готовится» навсегда: задание
упало, а интерфейс этого не знает. Проверяются все три исхода — готов, не построен,
преобразователь недоступен, — потому что путать второй с третьим значит навсегда лишить
предпросмотра файлы, загруженные в минуту перезапуска контейнера.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.preview import ConversionError, ConverterUnavailableError
from app.adapters.queue import RecordingQueue
from app.adapters.storage import StorageError
from app.adapters.storage.memory import InMemoryStorage
from app.adapters.storage.s3 import content_disposition
from app.domain.dictionaries import Priority, ProjectStatus
from app.domain.documents import (
    BY_EXTENSION,
    DocumentError,
    DocumentTarget,
    PreviewState,
    check_signature,
    check_size,
    extension_of,
    kind_of,
    megabytes,
    normalize_name,
    preview_key,
    storage_key,
)
from app.repos.models import AuditLog, Direction, Document, DocumentVersion, Project
from app.settings import Settings
from app.workers.jobs import build_preview_once
from tests.conftest import FakeScanner

pytestmark = pytest.mark.infra

API = "/api/v1"

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
XLSX = b"PK\x03\x04" + b"\x14\x00\x06\x00" + b"\x00" * 120
DOCX = b"PK\x03\x04" + b"\x14\x00\x08\x00" + b"\x00" * 200


async def a_project(session: AsyncSession, **overrides: Any) -> Project:
    direction = await session.scalar(select(Direction).limit(1))
    assert direction is not None

    fields: dict[str, Any] = {
        "code": f"PRJ-2026-{uuid.uuid4().int % 900 + 99:03d}",
        "title": "Проект с вложениями",
        "kind": "project",
        "share_externally": True,
        "direction_id": direction.id,
        "status_code": ProjectStatus.IN_PROGRESS.value,
        "priority_code": Priority.NORMAL.value,
        "started_on": date(2026, 1, 1),
        "due_on": date(2026, 12, 31),
    }
    fields.update(overrides)

    project = Project(**fields)
    session.add(project)
    await session.flush()
    return project


async def attach(
    api: AsyncClient,
    entity_id: Any,
    filename: str,
    content: bytes,
    entity_type: str = DocumentTarget.PROJECT.value,
) -> Any:
    return await api.post(
        f"{API}/documents",
        data={"entity_type": entity_type, "entity_id": str(entity_id)},
        files={"file": (filename, content, "application/octet-stream")},
    )


async def attached(api: AsyncClient, entity_id: Any) -> list[dict[str, Any]]:
    response = await api.get(
        f"{API}/documents",
        params={"entity_type": DocumentTarget.PROJECT.value, "entity_id": str(entity_id)},
    )
    assert response.status_code == 200, response.text
    listing: list[dict[str, Any]] = response.json()
    return listing


# --------------------------------------------------------------------------
# Имя, формат, размер — до всякой базы
# --------------------------------------------------------------------------


class TestWhatCountsAsAFile:
    def test_path_is_stripped_from_the_name(self) -> None:
        """Загрузка папкой присылает полный путь. Хранить его нельзя и показывать нечего."""
        assert normalize_name(r"C:\Users\Помощник\Документы\Смета.xlsx") == "Смета.xlsx"
        assert normalize_name("/home/user/Смета.xlsx") == "Смета.xlsx"

    def test_composed_and_decomposed_spelling_give_one_name(self) -> None:
        """«ё» с macOS приходит разложенной. Внешне имена одинаковы, байты — разные.

        Без приведения к одной форме у одного файла оказалось бы две карточки, и понять
        почему было бы невозможно: на экране они выглядят буквой в букву.
        """
        windows = "Приём.pdf"
        macos = "Прие\u0308м.pdf"
        assert windows != macos
        assert normalize_name(windows) == normalize_name(macos)

    def test_name_of_only_forbidden_characters_is_refused(self) -> None:
        with pytest.raises(DocumentError):
            normalize_name("??? ***")

    def test_unknown_extension_is_refused_and_the_message_lists_the_allowed(self) -> None:
        with pytest.raises(DocumentError) as refusal:
            kind_of("установщик.exe")
        message = str(refusal.value)
        assert "exe" in message
        assert "pdf" in message and "xlsx" in message

    def test_renamed_file_is_caught_by_its_first_bytes(self) -> None:
        """Расширение пишет тот, кто загружает. Подпись — тот, кто создал файл."""
        with pytest.raises(DocumentError) as refusal:
            check_signature(BY_EXTENSION["pdf"], XLSX[:16])
        assert "pdf" in str(refusal.value)

    def test_plain_text_has_no_signature_and_that_is_not_a_hole(self) -> None:
        check_signature(BY_EXTENSION["txt"], b"\xd0\x9f\xd1\x80\xd0\xb8\xd0\xb2\xd0\xb5\xd1\x82")

    def test_size_refusal_names_both_numbers(self) -> None:
        with pytest.raises(DocumentError) as refusal:
            check_size(60 * 1024 * 1024, limit=50 * 1024 * 1024)
        message = str(refusal.value)
        assert "60,0" in message and "50,0" in message

    def test_megabytes_are_written_the_way_they_are_read_here(self) -> None:
        assert megabytes(1536 * 1024) == "1,5"

    def test_extension_of_a_file_without_one_is_empty(self) -> None:
        assert extension_of("Смета") == ""
        assert extension_of("Смета.XLSX") == "xlsx"

    def test_storage_key_carries_the_owner(self) -> None:
        """По ключу видно, чей это файл, — иначе бакет нечем разобрать без базы."""
        key = storage_key(
            prefix="orbita",
            target=DocumentTarget.TASK,
            entity_id="task-1",
            document_id="doc-1",
            version=2,
            ext="xlsx",
        )
        assert key == "orbita/task/task-1/doc-1/v2.xlsx"
        assert preview_key(key) == "orbita/task/task-1/doc-1/v2.xlsx.preview.pdf"

    def test_svg_is_not_accepted(self) -> None:
        """Рисунок со сценарием внутри — не рисунок."""
        assert "svg" not in BY_EXTENSION

    def test_cyrillic_name_survives_the_download_header(self) -> None:
        """Имя уходит дважды: латиницей и по RFC 5987. Без второго файл сохранится как «_»."""
        header = content_disposition("Смета работ.xlsx", inline=False)
        assert header.startswith("attachment;")
        assert "filename*=UTF-8''%D0%A1%D0%BC%D0%B5%D1%82%D0%B0" in header
        assert 'filename="' in header

    def test_quotes_in_the_name_do_not_break_the_header(self) -> None:
        header = content_disposition('От"чёт.pdf', inline=True)
        assert header.count('"') == 2
        assert header.startswith("inline;")


# --------------------------------------------------------------------------
# Критерий 1: повторная загрузка того же имени — версия, а не второй документ
# --------------------------------------------------------------------------


class TestSameNameBecomesAVersion:
    async def test_second_upload_of_the_same_name_adds_a_version(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)

        first = await attach(assistant_api, project.id, "Смета.xlsx", XLSX)
        assert first.status_code == 201, first.text
        assert first.json()["document"]["current_version"] == 1

        second = await attach(assistant_api, project.id, "Смета.xlsx", XLSX + b"\x01")
        assert second.status_code == 201, second.text

        assert second.json()["document"]["id"] == first.json()["document"]["id"]
        assert second.json()["document"]["current_version"] == 2

        listing = await attached(assistant_api, project.id)
        assert len(listing) == 1, "два документа вместо двух версий одного"

    async def test_case_of_the_name_does_not_create_a_second_document(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """«Смета.xlsx» и «смета.xlsx» — один документ: регистр ставят не думая."""
        project = await a_project(session)
        await attach(assistant_api, project.id, "Смета.xlsx", XLSX)
        await attach(assistant_api, project.id, "смета.xlsx", XLSX + b"\x02")

        listing = await attached(assistant_api, project.id)
        assert len(listing) == 1
        assert listing[0]["current_version"] == 2

    async def test_versions_are_listed_newest_first(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        created = await attach(assistant_api, project.id, "Смета.xlsx", XLSX)
        document_id = created.json()["document"]["id"]
        await attach(assistant_api, project.id, "Смета.xlsx", XLSX + b"\x03")

        response = await assistant_api.get(f"{API}/documents/{document_id}/versions")
        assert response.status_code == 200
        numbers = [version["number"] for version in response.json()]
        assert numbers == [2, 1]

    async def test_each_version_lies_under_its_own_key(
        self, assistant_api: AsyncClient, session: AsyncSession, storage: InMemoryStorage
    ) -> None:
        """Иначе новая версия затирает предыдущую, и история есть только в базе."""
        project = await a_project(session)
        await attach(assistant_api, project.id, "Смета.xlsx", XLSX)
        await attach(assistant_api, project.id, "Смета.xlsx", XLSX + b"\x04")

        assert len(storage.objects) == 2
        assert sorted(key.rsplit("/", 1)[-1] for key in storage.objects) == ["v1.xlsx", "v2.xlsx"]


# --------------------------------------------------------------------------
# Критерий 2: то же содержимое новой версии не создаёт
# --------------------------------------------------------------------------


class TestSameContentCreatesNothing:
    async def test_identical_file_does_not_add_a_version(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        await attach(assistant_api, project.id, "Смета.xlsx", XLSX)
        again = await attach(assistant_api, project.id, "Смета.xlsx", XLSX)

        assert again.status_code == 201
        assert again.json()["created"] is False, (
            "интерфейсу нечем объяснить, почему ничего не произошло"
        )
        assert again.json()["document"]["current_version"] == 1

    async def test_identical_file_under_another_name_returns_the_first(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Тот же файл — тот же документ, как бы его ни назвали при второй загрузке.

        Две карточки на одно содержимое означают, что правку внесут в одну, а откроют
        другую (ADR-0009: дедупликация в пределах владельца).
        """
        project = await a_project(session)
        first = await attach(assistant_api, project.id, "Смета.xlsx", XLSX)
        renamed = await attach(assistant_api, project.id, "Смета итоговая.xlsx", XLSX)

        assert renamed.json()["created"] is False
        assert renamed.json()["document"]["id"] == first.json()["document"]["id"]
        assert renamed.json()["document"]["name"] == "Смета.xlsx"

        assert len(await attached(assistant_api, project.id)) == 1

    async def test_the_same_file_attaches_to_a_different_owner(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Дедупликация в пределах владельца, а не всей базы.

        Одна и та же форма отчёта прикладывается к десятку проектов, и «этот файл уже
        есть у другого проекта» означало бы, что приложить её второй раз нельзя.
        """
        one = await a_project(session)
        two = await a_project(session)

        await attach(assistant_api, one.id, "Форма.xlsx", XLSX)
        other = await attach(assistant_api, two.id, "Форма.xlsx", XLSX)

        assert other.json()["created"] is True
        assert len(await attached(assistant_api, two.id)) == 1

    async def test_nothing_is_written_to_storage_the_second_time(
        self, assistant_api: AsyncClient, session: AsyncSession, storage: InMemoryStorage
    ) -> None:
        project = await a_project(session)
        await attach(assistant_api, project.id, "Смета.xlsx", XLSX)
        assert len(storage.objects) == 1
        await attach(assistant_api, project.id, "Смета.xlsx", XLSX)
        assert len(storage.objects) == 1


# --------------------------------------------------------------------------
# Критерий 3: содержимое раздаётся ссылкой, а не приложением
# --------------------------------------------------------------------------


class TestContentLeavesByLink:
    async def test_link_points_at_storage_and_expires(
        self, assistant_api: AsyncClient, session: AsyncSession, storage: InMemoryStorage
    ) -> None:
        project = await a_project(session)
        created = await attach(assistant_api, project.id, "Смета.xlsx", XLSX)
        document_id = created.json()["document"]["id"]

        response = await assistant_api.get(f"{API}/documents/{document_id}/link")
        assert response.status_code == 200, response.text
        body = response.json()

        assert body["expires_in"] == 300
        assert body["filename"] == "Смета.xlsx"
        assert storage.links, "ссылка выдана не хранилищем"
        assert body["url"].startswith("memory://")

    async def test_the_api_never_answers_with_the_bytes(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Содержимое не проходит через приложение — иначе обработчик занят всю передачу."""
        project = await a_project(session)
        created = await attach(assistant_api, project.id, "Отчёт.pdf", PDF)
        document_id = created.json()["document"]["id"]

        for path in (
            f"{API}/documents/{document_id}/link",
            f"{API}/documents/{document_id}/versions",
        ):
            response = await assistant_api.get(path)
            assert PDF not in response.content

    async def test_the_link_lives_the_same_time_for_every_file(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Срок жизни ссылки один для всех — и это новое правило, а не упущение.

        Раньше файл проекта с грифом получал минуту вместо пяти, а выдача ссылки писалась
        в журнал. И то, и другое защищало от пересылки ссылки; пересылать её теперь
        некому — ссылку получают те же двое (ADR-0024, ADR-0011). Проверяется именно на
        непубличном проекте: у него срок обязан быть тем же, что у остальных.
        """
        private = await a_project(session, share_externally=False)
        created = await attach(assistant_api, private.id, "Смета.xlsx", XLSX)
        document_id = created.json()["document"]["id"]

        response = await assistant_api.get(f"{API}/documents/{document_id}/link")
        assert response.json()["expires_in"] == 300

    async def test_the_name_of_a_file_never_reaches_the_journal(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Журнал переживает и удаление проекта, и очистку хранилища.

        «Смета по объекту в Кашкадарье.xlsx» рассказывает о проекте столько же, сколько
        его название, а вторую копию из журнала уже не вычистить: он только на дозапись.
        Факт появления вложения при этом остаётся — иначе файл можно было бы приложить
        бесследно (ADR-0010).
        """
        project = await a_project(session)
        await attach(assistant_api, project.id, "Смета по объекту.xlsx", XLSX)

        entry = await session.scalar(
            select(AuditLog).where(
                AuditLog.entity_type == Document.__tablename__, AuditLog.action == "created"
            )
        )
        assert entry is not None, "появление вложения не попало в журнал вовсе"
        assert "name" in entry.changes, "непонятно даже, что именно менялось"
        assert "Смета" not in str(entry.changes)

    async def test_issuing_a_link_is_never_written_down(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Выдача ссылки в журнал не пишется — ни для какого файла.

        Писатель у действия `downloaded` был один, и он ушёл вместе с грифом (ADR-0024).
        Тест проверяет оба вида проекта, а не только обычный: иначе он остался бы зелёным
        и после того, как запись выдачи вернут «на всякий случай» для непубличных. Журнал,
        в который попадает каждое открытие каждого вложения, перестают читать — а вместе
        с ним перестают замечать записи, ради которых он заводился.
        """
        for shared in (True, False):
            project = await a_project(session, share_externally=shared)
            created = await attach(assistant_api, project.id, "Смета.xlsx", XLSX)
            await assistant_api.get(f"{API}/documents/{created.json()['document']['id']}/link")

        written = await session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "downloaded")
        )
        assert written == 0

    async def test_an_older_version_can_be_asked_for_by_number(
        self, assistant_api: AsyncClient, session: AsyncSession, storage: InMemoryStorage
    ) -> None:
        project = await a_project(session)
        created = await attach(assistant_api, project.id, "Смета.xlsx", XLSX)
        document_id = created.json()["document"]["id"]
        await attach(assistant_api, project.id, "Смета.xlsx", XLSX + b"\x05")

        response = await assistant_api.get(
            f"{API}/documents/{document_id}/link", params={"version": 1}
        )
        assert response.status_code == 200
        assert storage.links[-1].endswith("/v1.xlsx")

    async def test_a_version_that_never_existed_is_not_found(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        created = await attach(assistant_api, project.id, "Смета.xlsx", XLSX)
        document_id = created.json()["document"]["id"]

        response = await assistant_api.get(
            f"{API}/documents/{document_id}/link", params={"version": 9}
        )
        assert response.status_code == 404


# --------------------------------------------------------------------------
# Критерий 4: отказ понятен
# --------------------------------------------------------------------------


class TestRefusalsExplainThemselves:
    async def test_forbidden_type_is_refused_by_name(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        response = await attach(assistant_api, project.id, "установщик.exe", b"MZ\x90\x00")

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "exe" in detail and "xlsx" in detail

    async def test_renamed_file_is_refused_with_a_useful_hint(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        response = await attach(assistant_api, project.id, "Отчёт.pdf", XLSX)

        assert response.status_code == 422
        assert "расширение" in response.json()["detail"]

    async def test_oversized_file_is_refused_before_it_is_read(
        self, assistant_api: AsyncClient, session: AsyncSession, settings: Settings
    ) -> None:
        """Отказ по объявленному размеру: иначе файл сначала приедет целиком."""
        project = await a_project(session)
        settings.max_upload_mb = 1

        response = await attach(assistant_api, project.id, "Большой.pdf", PDF + b"\x00" * 2_000_000)

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "1,0" in detail and "МБ" in detail

    async def test_oversized_file_is_refused_even_without_a_declared_size(
        self, assistant_api: AsyncClient, session: AsyncSession, settings: Settings
    ) -> None:
        """Заявленному размеру не верят: настоящий считается по принятому содержимому."""
        project = await a_project(session)
        settings.max_upload_mb = 1

        response = await assistant_api.post(
            f"{API}/documents",
            data={"entity_type": DocumentTarget.PROJECT.value, "entity_id": str(project.id)},
            files={"file": ("Большой.pdf", PDF + b"\x00" * 2_000_000, "application/pdf")},
            headers={"Content-Length": "100"},
        )
        assert response.status_code == 422

    async def test_empty_file_is_refused(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        response = await attach(assistant_api, project.id, "Пусто.txt", b"")
        assert response.status_code == 422

    async def test_attachment_to_a_record_that_does_not_exist(
        self, assistant_api: AsyncClient
    ) -> None:
        response = await attach(assistant_api, uuid.uuid4(), "Смета.xlsx", XLSX)
        assert response.status_code == 404

    async def test_a_refused_file_leaves_nothing_behind(
        self, assistant_api: AsyncClient, session: AsyncSession, storage: InMemoryStorage
    ) -> None:
        project = await a_project(session)
        await attach(assistant_api, project.id, "установщик.exe", b"MZ\x90\x00")

        assert storage.objects == {}
        assert await session.scalar(select(func.count()).select_from(Document)) == 0


# --------------------------------------------------------------------------
# Антивирус (Q7)
# --------------------------------------------------------------------------


class TestAntivirusRunsBeforeAnythingIsKept:
    async def test_infected_file_is_not_stored_at_all(
        self,
        assistant_api: AsyncClient,
        session: AsyncSession,
        storage: InMemoryStorage,
        scanner: FakeScanner,
    ) -> None:
        """Не «сохраняется и прячется», а не сохраняется."""
        project = await a_project(session)
        scanner.infected.add(XLSX)

        response = await attach(assistant_api, project.id, "Смета.xlsx", XLSX)

        assert response.status_code == 422
        assert "антивирус" in response.json()["detail"].lower()
        assert storage.objects == {}
        assert await session.scalar(select(func.count()).select_from(Document)) == 0

    async def test_the_name_of_the_signature_is_not_shown(
        self, assistant_api: AsyncClient, session: AsyncSession, scanner: FakeScanner
    ) -> None:
        """По имени найденного подбирают то, чего антивирус не знает."""
        project = await a_project(session)
        scanner.infected.add(XLSX)

        response = await attach(assistant_api, project.id, "Смета.xlsx", XLSX)
        assert "Test.Signature" not in response.text

    async def test_unavailable_antivirus_forbids_the_upload(
        self,
        assistant_api: AsyncClient,
        session: AsyncSession,
        storage: InMemoryStorage,
        scanner: FakeScanner,
    ) -> None:
        """Иначе достаточно уронить антивирус, чтобы проверки не стало."""
        project = await a_project(session)
        scanner.unavailable = True

        response = await attach(assistant_api, project.id, "Смета.xlsx", XLSX)

        assert response.status_code == 503
        assert storage.objects == {}

    async def test_scanning_happens_before_storage(
        self, assistant_api: AsyncClient, session: AsyncSession, scanner: FakeScanner
    ) -> None:
        project = await a_project(session)
        await attach(assistant_api, project.id, "Смета.xlsx", XLSX)
        assert scanner.scanned == [len(XLSX)]


# --------------------------------------------------------------------------
# Критерий 5: предпросмотр
# --------------------------------------------------------------------------


class FakeConverter:
    """Преобразователь, исход которого назначает тест."""

    name = "fake"

    def __init__(self, result: bytes | Exception = b"%PDF-1.7 preview") -> None:
        self.result = result
        self.calls: list[str] = []

    async def to_pdf(self, data: bytes, *, filename: str) -> bytes:
        self.calls.append(filename)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class TestPreview:
    async def test_pdf_and_images_are_shown_as_they_are(
        self, assistant_api: AsyncClient, session: AsyncSession, queue: RecordingQueue
    ) -> None:
        """Производная от PDF — это вторая копия того же файла."""
        project = await a_project(session)

        for name, content in (("Отчёт.pdf", PDF), ("Схема.png", PNG)):
            created = await attach(assistant_api, project.id, name, content)
            assert created.json()["document"]["version"]["preview_state"] == "native"

        assert queue.jobs == [], "для показываемого браузером файла поставлено задание"

    async def test_office_file_waits_for_its_preview(
        self, assistant_api: AsyncClient, session: AsyncSession, queue: RecordingQueue
    ) -> None:
        project = await a_project(session)
        created = await attach(assistant_api, project.id, "Письмо.docx", DOCX)

        version_id = created.json()["document"]["version"]["id"]
        assert created.json()["document"]["version"]["preview_state"] == "pending"
        assert queue.jobs == [("build_preview", (version_id,), f"preview:{version_id}")]

    async def test_the_job_builds_the_pdf(
        self, assistant_api: AsyncClient, session: AsyncSession, storage: InMemoryStorage
    ) -> None:
        project = await a_project(session)
        created = await attach(assistant_api, project.id, "Письмо.docx", DOCX)
        version_id = uuid.UUID(created.json()["document"]["version"]["id"])

        converter = FakeConverter()
        assert await build_preview_once(session, storage, converter, version_id) is True

        version = await session.get(DocumentVersion, version_id)
        assert version is not None
        assert version.preview_state == PreviewState.READY.value
        assert version.preview_key is not None
        assert storage.objects[version.preview_key][0] == b"%PDF-1.7 preview"
        assert converter.calls == ["Письмо.docx"], "преобразователю не передали имя файла"

    async def test_the_job_does_nothing_the_second_time(
        self, assistant_api: AsyncClient, session: AsyncSession, storage: InMemoryStorage
    ) -> None:
        """Повторный запуск — обычное дело: воркер перезапускается (инвариант 6)."""
        project = await a_project(session)
        created = await attach(assistant_api, project.id, "Письмо.docx", DOCX)
        version_id = uuid.UUID(created.json()["document"]["version"]["id"])

        await build_preview_once(session, storage, FakeConverter(), version_id)
        second = FakeConverter(b"%PDF-1.7 second")
        assert await build_preview_once(session, storage, second, version_id) is False
        assert second.calls == []

    async def test_a_file_that_cannot_be_converted_says_so(
        self, assistant_api: AsyncClient, session: AsyncSession, storage: InMemoryStorage
    ) -> None:
        project = await a_project(session)
        created = await attach(assistant_api, project.id, "Письмо.docx", DOCX)
        version_id = uuid.UUID(created.json()["document"]["version"]["id"])

        converter = FakeConverter(ConversionError("файл повреждён"))
        assert await build_preview_once(session, storage, converter, version_id) is False

        version = await session.get(DocumentVersion, version_id)
        assert version is not None
        assert version.preview_state == PreviewState.FAILED.value

    async def test_an_unavailable_converter_leaves_the_state_alone(
        self, assistant_api: AsyncClient, session: AsyncSession, storage: InMemoryStorage
    ) -> None:
        """«Готовится» — правда: преобразователь вернётся, и задание повторится.

        Пометь мы здесь «не построен», один перезапуск контейнера навсегда лишил бы
        предпросмотра все файлы, загруженные в эту минуту.
        """
        project = await a_project(session)
        created = await attach(assistant_api, project.id, "Письмо.docx", DOCX)
        version_id = uuid.UUID(created.json()["document"]["version"]["id"])

        converter = FakeConverter(ConverterUnavailableError("контейнер перезапускается"))
        with pytest.raises(ConverterUnavailableError):
            await build_preview_once(session, storage, converter, version_id)

        version = await session.get(DocumentVersion, version_id)
        assert version is not None
        assert version.preview_state == PreviewState.PENDING.value

    async def test_a_version_not_yet_committed_is_retried(
        self, session: AsyncSession, storage: InMemoryStorage
    ) -> None:
        """Задание ставится до фиксации транзакции запроса — «нет записи» бывает законно."""
        with pytest.raises(LookupError):
            await build_preview_once(session, storage, FakeConverter(), uuid.uuid4())

    async def test_inline_link_opens_the_derived_pdf(
        self, assistant_api: AsyncClient, session: AsyncSession, storage: InMemoryStorage
    ) -> None:
        """Браузер не откроет таблицу. Ради этого производный PDF и строится."""
        project = await a_project(session)
        created = await attach(assistant_api, project.id, "Письмо.docx", DOCX)
        document_id = created.json()["document"]["id"]
        version_id = uuid.UUID(created.json()["document"]["version"]["id"])

        await build_preview_once(session, storage, FakeConverter(), version_id)

        response = await assistant_api.get(
            f"{API}/documents/{document_id}/link", params={"inline": True}
        )
        assert response.status_code == 200
        assert storage.links[-1].endswith(".preview.pdf")
        assert response.json()["filename"].endswith(".pdf")

    async def test_download_link_always_gives_the_original(
        self, assistant_api: AsyncClient, session: AsyncSession, storage: InMemoryStorage
    ) -> None:
        """Сохранить надо таблицу, а не её отпечаток."""
        project = await a_project(session)
        created = await attach(assistant_api, project.id, "Письмо.docx", DOCX)
        document_id = created.json()["document"]["id"]
        version_id = uuid.UUID(created.json()["document"]["version"]["id"])

        await build_preview_once(session, storage, FakeConverter(), version_id)

        await assistant_api.get(f"{API}/documents/{document_id}/link")
        assert storage.links[-1].endswith(".docx")


# --------------------------------------------------------------------------
# Удаление
# --------------------------------------------------------------------------


class TestRemoval:
    async def test_deleted_document_leaves_the_list_but_not_the_base(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        created = await attach(assistant_api, project.id, "Смета.xlsx", XLSX)
        document_id = created.json()["document"]["id"]

        response = await assistant_api.delete(f"{API}/documents/{document_id}")
        assert response.status_code == 204

        assert await attached(assistant_api, project.id) == []
        assert (
            await session.scalar(
                select(func.count())
                .select_from(DocumentVersion)
                .where(DocumentVersion.document_id == uuid.UUID(document_id))
            )
            == 1
        )

    async def test_the_name_is_free_again_after_deletion(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Удалили по ошибке — загружают заново. Это первое, что человек попробует."""
        project = await a_project(session)
        created = await attach(assistant_api, project.id, "Смета.xlsx", XLSX)
        await assistant_api.delete(f"{API}/documents/{created.json()['document']['id']}")

        again = await attach(assistant_api, project.id, "Смета.xlsx", XLSX + b"\x06")
        assert again.status_code == 201, again.text
        assert again.json()["document"]["id"] != created.json()["document"]["id"]

    async def test_deleting_the_project_takes_its_files_with_it(
        self, assistant_api: AsyncClient, session: AsyncSession, storage: InMemoryStorage
    ) -> None:
        """Владельца нет — файл не найти ничем. Хранить его негде и незачем."""
        project = await a_project(session)
        await attach(assistant_api, project.id, "Смета.xlsx", XLSX)
        assert len(storage.objects) == 1

        response = await assistant_api.delete(f"{API}/projects/{project.id}")
        assert response.status_code == 204, response.text

        assert await session.scalar(select(func.count()).select_from(Document)) == 0
        assert storage.objects == {}

    async def test_deleting_a_task_takes_its_files_with_it(
        self, assistant_api: AsyncClient, session: AsyncSession, storage: InMemoryStorage
    ) -> None:
        task = await assistant_api.post(
            f"{API}/tasks",
            json={"title": "Задача с файлом", "priority_code": Priority.NORMAL.value},
        )
        task_id = task.json()["id"]
        await attach(assistant_api, task_id, "Смета.xlsx", XLSX, DocumentTarget.TASK.value)

        assert (await assistant_api.delete(f"{API}/tasks/{task_id}")).status_code == 204
        assert await session.scalar(select(func.count()).select_from(Document)) == 0
        assert storage.objects == {}

    async def test_files_of_a_project_task_go_with_the_project(
        self, assistant_api: AsyncClient, session: AsyncSession, storage: InMemoryStorage
    ) -> None:
        """База уносит задачи каскадом, а их вложения — нет: связь ей не выразить."""
        project = await a_project(session)
        task = await assistant_api.post(
            f"{API}/tasks",
            json={
                "title": "Задача проекта",
                "priority_code": Priority.NORMAL.value,
                "project_id": str(project.id),
            },
        )
        await attach(
            assistant_api, task.json()["id"], "Смета.xlsx", XLSX, DocumentTarget.TASK.value
        )

        await assistant_api.delete(f"{API}/projects/{project.id}")

        assert await session.scalar(select(func.count()).select_from(Document)) == 0
        assert storage.objects == {}

    async def test_unreachable_storage_does_not_block_the_deletion(
        self, assistant_api: AsyncClient, session: AsyncSession, storage: InMemoryStorage
    ) -> None:
        """Несогласованная база — беда без хозяина; лишний объект в бакете — нет."""
        project = await a_project(session)
        await attach(assistant_api, project.id, "Смета.xlsx", XLSX)

        async def refuse(keys: Any) -> None:
            raise StorageError("хранилище недоступно")

        storage.delete = refuse  # type: ignore[method-assign]

        response = await assistant_api.delete(f"{API}/projects/{project.id}")
        assert response.status_code == 204
        assert await session.scalar(select(func.count()).select_from(Document)) == 0


# --------------------------------------------------------------------------
# Кто что может (ADR-0011)
# --------------------------------------------------------------------------


class TestWhoMayDoWhat:
    async def test_the_leader_reads_but_does_not_attach(
        self, leader_api: AsyncClient, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        project = await a_project(session)
        await attach(assistant_api, project.id, "Смета.xlsx", XLSX)

        listing = await leader_api.get(
            f"{API}/documents",
            params={"entity_type": DocumentTarget.PROJECT.value, "entity_id": str(project.id)},
        )
        assert listing.status_code == 200
        assert len(listing.json()) == 1

        refused = await attach(leader_api, project.id, "Своё.pdf", PDF)
        assert refused.status_code == 403

    async def test_the_leader_may_take_a_link(
        self, leader_api: AsyncClient, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Смотреть — его работа. Ссылка нужна, чтобы открыть файл (ADR-0011)."""
        project = await a_project(session)
        created = await attach(assistant_api, project.id, "Смета.xlsx", XLSX)

        response = await leader_api.get(f"{API}/documents/{created.json()['document']['id']}/link")
        assert response.status_code == 200

    async def test_without_a_role_header_the_list_still_works(
        self, api: AsyncClient, session: AsyncSession
    ) -> None:
        """Входа в системе нет (ADR-0026): не назвавшийся считается помощником.

        Раньше здесь ожидался 401. Теперь отсутствие заголовка роли — не отказ, а
        умолчание, и проверка сторожит именно это: список обязан открыться, а не
        промолчать.
        """
        project = await a_project(session)
        response = await api.get(
            f"{API}/documents",
            params={"entity_type": DocumentTarget.PROJECT.value, "entity_id": str(project.id)},
        )
        assert response.status_code == 200


# --------------------------------------------------------------------------
# Хранилище в памяти — само по себе
# --------------------------------------------------------------------------


class TestInMemoryStorageIsNotAPretence:
    async def test_it_gives_back_what_it_was_given(self) -> None:
        """Подделка, которая всё принимает и ничего не помнит, проходит любой тест."""
        storage = InMemoryStorage()
        await storage.put("ключ", "содержимое".encode(), content_type="text/plain")
        assert await storage.get("ключ") == "содержимое".encode()

    async def test_a_missing_object_is_an_error(self) -> None:
        storage = InMemoryStorage()
        with pytest.raises(StorageError):
            await storage.get("нет такого")

    async def test_the_link_carries_the_lifetime(self) -> None:
        storage = InMemoryStorage()
        await storage.put("ключ", b"x", content_type="text/plain")
        url = await storage.link(
            "ключ",
            filename="Смета.xlsx",
            content_type="text/plain",
            inline=False,
            lifetime=timedelta(seconds=42),
        )
        assert "expires=42" in url
