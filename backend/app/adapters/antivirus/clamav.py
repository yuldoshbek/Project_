"""ClamAV по протоколу clamd (Q7).

Команда `INSTREAM`: содержимое передаётся в сокет кусками, каждому предшествует его длина
четырьмя байтами, конец обозначается нулевой длиной. Файл не кладётся во временную папку
и не показывается антивирусу по пути — иначе проверяющий и проверяемый оказались бы в
разных контейнерах с разным представлением о файловой системе, и проверка превратилась бы
в «файл не найден, считаем чистым».

Библиотеки для этого нет намеренно: `python-clamd` синхронна, и её вызов остановил бы
цикл событий на всё время проверки — то есть на всё то время, ради сокращения которого
приложение и сделано асинхронным. Протокол же занимает тридцать строк.
"""

from __future__ import annotations

import asyncio
import struct

import structlog

from app.adapters.antivirus import AntivirusUnavailableError, ScanResult
from app.settings import Settings

logger = structlog.get_logger(__name__)

CHUNK = 64 * 1024
"""Размер куска передачи. Больше `StreamMaxLength` clamd не примет, меньше — медленнее."""

END_OF_STREAM = struct.pack("!L", 0)

MAX_REPLY = 4096
"""Ответ clamd — одна строка. Больше читать незачем и опасно: поток мог не закрыться."""


class ClamAvScanner:
    """Проверка содержимого демоном clamd по TCP."""

    name = "clamav"

    def __init__(self, settings: Settings) -> None:
        self._host = settings.antivirus_host
        self._port = settings.antivirus_port
        self._timeout = settings.antivirus_timeout_seconds

    async def scan(self, data: bytes) -> ScanResult:
        try:
            async with asyncio.timeout(self._timeout):
                reply = await self._instream(data)
        except TimeoutError as error:
            raise AntivirusUnavailableError(
                f"антивирус не ответил за {self._timeout:.0f} с"
            ) from error
        except OSError as error:
            raise AntivirusUnavailableError(str(error)) from error

        return self._verdict(reply)

    async def _instream(self, data: bytes) -> str:
        reader, writer = await asyncio.open_connection(self._host, self._port)
        try:
            writer.write(b"zINSTREAM\x00")
            for start in range(0, len(data), CHUNK):
                piece = data[start : start + CHUNK]
                writer.write(struct.pack("!L", len(piece)) + piece)
                await writer.drain()
            writer.write(END_OF_STREAM)
            await writer.drain()

            raw = await reader.read(MAX_REPLY)
        finally:
            writer.close()
            # Гасим ошибку закрытия: сам ответ уже получен, и падать на прощании с
            # сокетом значило бы отклонить проверенный файл.
            try:  # noqa: SIM105
                await writer.wait_closed()
            except OSError:
                pass

        return raw.decode("utf-8", errors="replace").strip().strip("\x00")

    def _verdict(self, reply: str) -> ScanResult:
        """Разбор ответа `stream: OK` / `stream: <имя> FOUND` / `... ERROR`.

        Неизвестный ответ считается недоступностью, а не чистотой: ответ, который мы не
        умеем прочитать, — это отсутствующая проверка.
        """
        if reply.endswith("OK"):
            return ScanResult(is_clean=True)

        if reply.endswith("FOUND"):
            signature = reply.removeprefix("stream:").removesuffix("FOUND").strip()
            logger.warning("antivirus_found", signature=signature)
            return ScanResult(is_clean=False, signature=signature or None)

        logger.error("antivirus_unexpected_reply", reply=reply)
        raise AntivirusUnavailableError(f"непонятный ответ антивируса: {reply!r}")
