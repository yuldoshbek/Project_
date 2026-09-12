"""S3-совместимое хранилище. В разработке — MinIO, на рабочем контуре — оно же или S3.

**Клиент создаётся на каждую операцию.** Держать его открытым на всё время жизни
приложения быстрее на десяток миллисекунд, но требует закрывать соединение при остановке
и заново открывать после обрыва — а вложения загружают несколько раз в день. Плата за
простоту здесь заведомо меньше платы за ещё один объект с жизненным циклом.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any
from urllib.parse import quote

import aioboto3
import structlog
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.adapters.storage import StorageError
from app.settings import Settings

logger = structlog.get_logger(__name__)


def content_disposition(filename: str, *, inline: bool) -> str:
    """Заголовок, по которому браузер решает — показать файл или сохранить.

    Имя передаётся дважды: обычным параметром и по RFC 5987. Первый обязан быть из одних
    латинских букв — браузер, не понявший второй, сохранит файл под ним; кириллица в
    неэкранированном виде ломает разбор заголовка целиком, и тогда теряется даже
    `attachment`. Второй несёт настоящее имя: «Смета работ.xlsx», а не «_____ _____.xlsx».
    """
    ascii_name = "".join(char if 32 < ord(char) < 127 and char != '"' else "_" for char in filename)
    escaped = quote(filename, safe="")
    kind = "inline" if inline else "attachment"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{escaped}"


class S3Storage:
    """Хранилище поверх S3 API."""

    name = "s3"

    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.s3_bucket
        self._session = aioboto3.Session()
        self._options: dict[str, Any] = {
            "endpoint_url": settings.s3_endpoint,
            "aws_access_key_id": settings.s3_access_key.get_secret_value(),
            "aws_secret_access_key": settings.s3_secret_key.get_secret_value(),
            "region_name": settings.s3_region,
            # Путь, а не поддомен: у MinIO по адресу `127.0.0.1` поддомена быть не может,
            # и запрос ушёл бы на несуществующее имя `orbita.127.0.0.1`.
            "config": Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3},
            ),
        }

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[Any]:
        """Клиент S3 с переводом ошибок библиотеки в ошибку порта."""
        try:
            async with self._session.client("s3", **self._options) as client:
                yield client
        except (BotoCoreError, ClientError, OSError) as error:
            logger.error("storage_failed", error=str(error))
            raise StorageError(str(error)) from error

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        async with self._client() as client:
            await client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )

    async def get(self, key: str) -> bytes:
        async with self._client() as client:
            response = await client.get_object(Bucket=self._bucket, Key=key)
            async with response["Body"] as stream:
                data: bytes = await stream.read()
                return data

    async def delete(self, keys: Sequence[str]) -> None:
        if not keys:
            return
        async with self._client() as client:
            await client.delete_objects(
                Bucket=self._bucket,
                Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
            )

    async def link(
        self,
        key: str,
        *,
        filename: str,
        content_type: str,
        inline: bool,
        lifetime: timedelta,
    ) -> str:
        async with self._client() as client:
            url: str = await client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._bucket,
                    "Key": key,
                    "ResponseContentType": content_type,
                    "ResponseContentDisposition": content_disposition(filename, inline=inline),
                },
                ExpiresIn=int(lifetime.total_seconds()),
            )
            return url
