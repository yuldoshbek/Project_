"""Хранилище, антивирус и преобразователь — то, что говорит с чужими программами.

Настоящие clamd и LibreOffice в наборе тестов не поднимаются: гигабайт сигнатур и два
гигабайта офисного пакета проверяли бы заодно сеть, образы и свежесть баз — и падали бы
по любой из этих причин, ничего не сообщая о нашем коде. Вместо них здесь **поддельный
собеседник**, говорящий на том же протоколе: он отвечает так, как отвечает настоящий, и
запоминает, что ему прислали.

Это разные вещи — «подделать чужую программу» и «подделать свой адаптер». Второе
проверяло бы, что мы умеем вызывать собственный метод. Здесь проверяется то, что ломается
молча: обрамление потока у clamd (длина куском, нулевая длина в конце), разбор его ответа
и то, какие отказы преобразователя стоит повторять, а какие бессмысленно.

Хранилище — исключение: оно проверяется **настоящее**, в MinIO из `make up`. Подписанная
ссылка либо работает у стороннего сервера, либо нет, и подделка тут не докажет ничего.
"""

from __future__ import annotations

import asyncio
import contextlib
import struct
from collections.abc import AsyncIterator, Callable
from datetime import timedelta
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.adapters.antivirus import (
    AntivirusUnavailableError,
    create_virus_scanner,
)
from app.adapters.antivirus.clamav import ClamAvScanner
from app.adapters.antivirus.disabled import NoScanner
from app.adapters.preview import (
    ConversionError,
    ConverterUnavailableError,
    create_document_converter,
)
from app.adapters.preview.disabled import NoConverter
from app.adapters.preview.gotenberg import GotenbergConverter
from app.adapters.storage import StorageError, create_file_storage
from app.adapters.storage.s3 import S3Storage
from app.settings import Settings

EICAR_SHAPED = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$FAKE-NOT-A-REAL-SIGNATURE$H+H*"
"""Похоже на пробный образец, но им не является.

Настоящую строку EICAR в репозиторий класть нельзя: антивирус на машине разработчика
удалит файл вместе с тестом, и набор тестов перестанет собираться по причине, которую
будут искать полдня. Здесь она и не нужна — приговор выносит поддельный clamd.
"""


# --------------------------------------------------------------------------
# Поддельный clamd
# --------------------------------------------------------------------------


@contextlib.asynccontextmanager
async def clamd_answering(
    reply: bytes, *, received: list[bytes] | None = None, hang: bool = False
) -> AsyncIterator[int]:
    """Сервер, говорящий на протоколе clamd. Возвращает порт, на котором слушает."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.readuntil(b"\x00")
            payload = bytearray()
            while True:
                size = struct.unpack("!L", await reader.readexactly(4))[0]
                if size == 0:
                    break
                payload += await reader.readexactly(size)
            if received is not None:
                received.append(bytes(payload))
            if hang:
                await asyncio.sleep(30)
            writer.write(reply)
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port: int = server.sockets[0].getsockname()[1]
    async with server:
        yield port


def scanner_for(port: int, *, timeout: float = 5.0) -> ClamAvScanner:
    return ClamAvScanner(
        Settings(
            secret_key=SecretStr("тестовый-ключ-достаточной-длины-не-для-эксплуатации"),
            antivirus_host="127.0.0.1",
            antivirus_port=port,
            antivirus_timeout_seconds=timeout,
        )
    )


class TestTheConversationWithClamd:
    async def test_a_clean_file_is_reported_clean(self) -> None:
        async with clamd_answering(b"stream: OK\x00") as port:
            assert (await scanner_for(port).scan("обычный файл".encode())).is_clean

    async def test_the_whole_file_reaches_the_scanner(self) -> None:
        """Обрамление потока ломается тихо: проверят половину файла и скажут «чисто».

        Куски передаются с длиной впереди, конец обозначается нулевой длиной. Ошибись
        здесь — и clamd увидит обрезанное содержимое, а ответит по нему «OK».
        """
        received: list[bytes] = []
        payload = bytes(range(256)) * 700  # больше одного куска передачи

        async with clamd_answering(b"stream: OK\x00", received=received) as port:
            await scanner_for(port).scan(payload)

        assert received == [payload]

    async def test_a_found_signature_is_reported(self) -> None:
        async with clamd_answering(b"stream: Win.Test.EICAR_HDB-1 FOUND\x00") as port:
            verdict = await scanner_for(port).scan(EICAR_SHAPED)

        assert verdict.is_clean is False
        assert verdict.signature == "Win.Test.EICAR_HDB-1"

    async def test_an_error_reply_is_not_a_clean_verdict(self) -> None:
        """«ERROR» — это непроверенный файл, а не проверенный.

        Считать иначе значит, что переполненный clamd молча пропускает всё подряд.
        """
        async with clamd_answering(b"INSTREAM size limit exceeded. ERROR\x00") as port:
            with pytest.raises(AntivirusUnavailableError):
                await scanner_for(port).scan("большой файл".encode())

    async def test_an_unreadable_reply_is_not_a_clean_verdict_either(self) -> None:
        async with clamd_answering(b"\x00") as port:
            with pytest.raises(AntivirusUnavailableError):
                await scanner_for(port).scan("файл".encode())

    async def test_a_silent_scanner_is_unavailable_not_permissive(self) -> None:
        async with clamd_answering(b"stream: OK\x00", hang=True) as port:
            with pytest.raises(AntivirusUnavailableError) as refusal:
                await scanner_for(port, timeout=0.3).scan("файл".encode())
        assert "не ответил" in str(refusal.value)

    async def test_nobody_listening_is_unavailable(self) -> None:
        async with clamd_answering(b"stream: OK\x00") as port:
            pass  # сервер закрылся — порт свободен

        with pytest.raises(AntivirusUnavailableError):
            await scanner_for(port).scan("файл".encode())


class TestChoosingTheScanner:
    def test_disabled_is_named_honestly_and_passes_everything(self) -> None:
        assert NoScanner().name == "disabled"

    async def test_disabled_reports_clean(self) -> None:
        assert (await NoScanner().scan("что угодно".encode())).is_clean

    def test_an_unknown_name_stops_the_application(self) -> None:
        """Опечатка в названии антивируса не должна молча означать «проверок нет»."""
        settings = Settings(
            secret_key=SecretStr("тестовый-ключ-достаточной-длины-не-для-эксплуатации"),
            antivirus="clamvav",
        )
        with pytest.raises(ValueError, match="неизвестный антивирус"):
            create_virus_scanner(settings)

    def test_both_known_names_resolve(self) -> None:
        def settings_with(name: str) -> Settings:
            return Settings(
                secret_key=SecretStr("тестовый-ключ-достаточной-длины-не-для-эксплуатации"),
                antivirus=name,
            )

        assert create_virus_scanner(settings_with("clamav")).name == "clamav"
        assert create_virus_scanner(settings_with("disabled")).name == "disabled"


# --------------------------------------------------------------------------
# Преобразователь
# --------------------------------------------------------------------------


def converter_answering(
    handler: Callable[[httpx.Request], httpx.Response], monkeypatch: pytest.MonkeyPatch
) -> GotenbergConverter:
    """Преобразователь, чьи запросы перехватывает `handler`.

    Подменяется клиент, а не наш код: адаптер строит запрос и разбирает ответ ровно так
    же, как в бою, — меняется только то, кто на том конце.
    """
    original = httpx.AsyncClient

    def with_stub(**kwargs: Any) -> httpx.AsyncClient:
        return original(transport=httpx.MockTransport(handler), **kwargs)

    # Подменяется сам `httpx`, а не поле в нашем модуле: адаптер обращается к библиотеке
    # по имени, и подмена через его пространство имён проверяла бы, что мы правильно
    # подменили, а не что адаптер правильно спрашивает. `monkeypatch` вернёт всё обратно.
    monkeypatch.setattr(httpx, "AsyncClient", with_stub)
    return GotenbergConverter(
        Settings(
            secret_key=SecretStr("тестовый-ключ-достаточной-длины-не-для-эксплуатации"),
            preview_url="http://converter:3000",
        )
    )


class TestTheConversationWithTheConverter:
    async def test_the_file_goes_with_its_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """По расширению преобразователь выбирает фильтр: без имени таблица и
        презентация для него — одинаковые zip-архивы."""
        seen: list[bytes] = []

        def answer(request: httpx.Request) -> httpx.Response:
            seen.append(request.content)
            return httpx.Response(200, content=b"%PDF-1.7 ok")

        converter = converter_answering(answer, monkeypatch)
        content = b"PK" + "данные".encode()
        assert await converter.to_pdf(content, filename="Смета.xlsx") == b"%PDF-1.7 ok"

        body = seen[0]
        assert b"PK\x03\x04" in body
        assert "Смета.xlsx".encode() in body

    async def test_the_path_is_the_office_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[str] = []

        def answer(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return httpx.Response(200, content=b"%PDF")

        converter = converter_answering(answer, monkeypatch)
        await converter.to_pdf(b"x", filename="Письмо.docx")
        assert seen == ["http://converter:3000/forms/libreoffice/convert"]

    async def test_a_refused_file_is_not_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Через минуту файл не станет другим."""
        converter = converter_answering(
            lambda request: httpx.Response(400, text="invalid document"), monkeypatch
        )
        with pytest.raises(ConversionError):
            await converter.to_pdf("повреждённый".encode(), filename="Письмо.docx")

    async def test_a_broken_converter_is_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """А контейнер — вернётся."""
        converter = converter_answering(
            lambda request: httpx.Response(502, text="bad gateway"), monkeypatch
        )
        with pytest.raises(ConverterUnavailableError):
            await converter.to_pdf("обычный".encode(), filename="Письмо.docx")

    async def test_a_silent_converter_is_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("соединение отклонено")

        converter = converter_answering(refuse, monkeypatch)
        with pytest.raises(ConverterUnavailableError):
            await converter.to_pdf("обычный".encode(), filename="Письмо.docx")

    async def test_the_answer_of_a_foreign_system_does_not_reach_the_user(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Английский текст чужой библиотеки в сообщении об ошибке — не сообщение."""
        converter = converter_answering(
            lambda request: httpx.Response(400, text="Error: could not parse OOXML"), monkeypatch
        )
        with pytest.raises(ConversionError) as refusal:
            await converter.to_pdf(b"x", filename="Письмо.docx")
        assert "OOXML" not in str(refusal.value)


class TestChoosingTheConverter:
    async def test_disabled_refuses_at_once(self) -> None:
        """Не пустой PDF: пустая страница читается как «таблица пустая»."""
        with pytest.raises(ConversionError):
            await NoConverter().to_pdf(b"x", filename="Письмо.docx")

    def test_an_unknown_name_stops_the_application(self) -> None:
        settings = Settings(
            secret_key=SecretStr("тестовый-ключ-достаточной-длины-не-для-эксплуатации"),
            preview_converter="libreoffice",
        )
        with pytest.raises(ValueError, match="неизвестный преобразователь"):
            create_document_converter(settings)

    def test_both_known_names_resolve(self) -> None:
        def settings_with(name: str) -> Settings:
            return Settings(
                secret_key=SecretStr("тестовый-ключ-достаточной-длины-не-для-эксплуатации"),
                preview_converter=name,
            )

        assert create_document_converter(settings_with("gotenberg")).name == "gotenberg"
        assert create_document_converter(settings_with("disabled")).name == "disabled"


# --------------------------------------------------------------------------
# Хранилище — настоящее
# --------------------------------------------------------------------------


@pytest.fixture
def s3(settings: Settings) -> S3Storage:
    storage = create_file_storage(settings)
    assert isinstance(storage, S3Storage)
    return storage


@pytest.mark.infra
class TestTheRealStorage:
    """Против MinIO из `make up`.

    Подписанная ссылка либо принимается сторонним сервером, либо нет: подпись собирается
    из области, метода, срока и заголовков, и ошибка в любом из них даёт ссылку, которая
    выглядит настоящей и отвечает отказом. Проверить это подделкой невозможно — она
    примет любую подпись.
    """

    KEY = "orbita/tests/вложение-проверка.txt"
    CONTENT = "содержимое с кириллицей".encode()

    async def test_what_was_put_comes_back(self, s3: S3Storage) -> None:
        await s3.put(self.KEY, self.CONTENT, content_type="text/plain; charset=utf-8")
        try:
            assert await s3.get(self.KEY) == self.CONTENT
        finally:
            await s3.delete([self.KEY])

    async def test_the_signed_link_actually_serves_the_file(self, s3: S3Storage) -> None:
        await s3.put(self.KEY, self.CONTENT, content_type="text/plain; charset=utf-8")
        try:
            url = await s3.link(
                self.KEY,
                filename="Проверка ссылки.txt",
                content_type="text/plain; charset=utf-8",
                inline=False,
                lifetime=timedelta(minutes=5),
            )
            async with httpx.AsyncClient(
                timeout=15, limits=httpx.Limits(max_keepalive_connections=0)
            ) as client:
                response = await client.get(url)

            assert response.status_code == 200, response.text
            assert response.content == self.CONTENT
            # Имя файла возвращается тем, кто его скачивает: в хранилище он лежит под
            # ключом вида «v1.txt», и без этого на диск сохранился бы файл «v1».
            # Кириллица едет по RFC 5987: в самом заголовке её нет и быть не может —
            # он только из латинских букв.
            disposition = response.headers["content-disposition"]
            assert (
                "filename*=UTF-8''%D0%9F%D1%80%D0%BE%D0%B2%D0%B5%D1%80%D0%BA%D0%B0" in disposition
            )
            assert disposition.startswith("attachment;")
        finally:
            await s3.delete([self.KEY])

    async def test_an_expired_link_stops_working(self, s3: S3Storage) -> None:
        """Срок жизни — единственное, что мешает пересланной ссылке жить вечно."""
        await s3.put(self.KEY, self.CONTENT, content_type="text/plain")
        try:
            url = await s3.link(
                self.KEY,
                filename="Проверка.txt",
                content_type="text/plain",
                inline=False,
                lifetime=timedelta(seconds=1),
            )
            await asyncio.sleep(1.5)
            async with httpx.AsyncClient(
                timeout=15, limits=httpx.Limits(max_keepalive_connections=0)
            ) as client:
                response = await client.get(url)

            assert response.status_code == 403, "ссылка пережила свой срок"
        finally:
            await s3.delete([self.KEY])

    async def test_a_missing_object_is_an_error_of_ours_not_of_the_library(
        self, s3: S3Storage
    ) -> None:
        """Слой выше не должен знать, что внизу S3, — иначе его не заменить."""
        with pytest.raises(StorageError):
            await s3.get("orbita/tests/такого-ключа-нет")

    async def test_deleting_what_is_not_there_is_not_a_failure(self, s3: S3Storage) -> None:
        await s3.delete(["orbita/tests/такого-ключа-нет"])
        await s3.delete([])
