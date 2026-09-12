"""LibreOffice в отдельном контейнере, за HTTP (ADR-0009).

Gotenberg — это тот самый headless LibreOffice, о котором говорит ADR, с HTTP-обёрткой
поверх. Обёртка здесь существенна: сам LibreOffice запускают командой, и запуск команды
означал бы, что офисный пакет установлен там же, где приложение. На машине разработчика
под Windows его нет, в образе приложения его быть не должно — это семьсот мегабайт ради
одного вызова, — а в двух разных местах он однажды окажется разных версий и даст два
разных PDF из одного файла.
"""

from __future__ import annotations

import httpx
import structlog

from app.adapters.preview import ConversionError, ConverterUnavailableError
from app.settings import Settings

logger = structlog.get_logger(__name__)

CONVERT_PATH = "/forms/libreoffice/convert"


class GotenbergConverter:
    """Преобразование офисных форматов в PDF по HTTP."""

    name = "gotenberg"

    def __init__(self, settings: Settings) -> None:
        self._url = settings.preview_url.rstrip("/") + CONVERT_PATH
        self._timeout = settings.preview_timeout_seconds

    async def to_pdf(self, data: bytes, *, filename: str) -> bytes:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._url, files={"files": (filename, data, "application/octet-stream")}
                )
        except httpx.HTTPError as error:
            logger.error("preview_transport_failed", error=str(error))
            raise ConverterUnavailableError(str(error)) from error

        if response.status_code == httpx.codes.OK:
            return response.content

        # Текст ответа — в лог, не наружу: он от чужой системы и на английском.
        logger.error("preview_refused", status=response.status_code, detail=response.text[:500])

        if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR:
            raise ConverterUnavailableError(f"преобразователь ответил {response.status_code}")
        # 4xx — претензия к файлу, а не к преобразователю: повторять нечего.
        raise ConversionError(f"преобразователь отклонил файл: {response.status_code}")
