"""Порт `FileStorage`: куда браузер кладёт файл и откуда его берёт (ADR-0009, ADR-0028).

Три реализации, выбираются настройкой `ORBITA_STORAGE` (`app.settings.Settings.storage_kind`):

- **локальная** — каталог на диске: разработка, тесты и сервер агентства с примонтированным
  томом. Загрузка и скачивание идут через API — лимита функции тут нет;
- **S3** — любое S3-совместимое хранилище (AWS Франкфурт, Cloudflare R2, сервер агентства):
  браузер грузит и скачивает **сам** по подписанной ссылке, мимо API — тело запроса к функции
  Vercel ограничено 4,5 МБ, а презентация весит больше;
- **нет** — хранилище не настроено: честный отказ вместо файла, который пропадёт.

Подпись S3 (SigV4, «query string») — своя, на stdlib: ради трёх подписанных ссылок тянуть
boto3 значило бы добавить в развёртывание десятки мегабайт (LIMITS, Л5).
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, urlsplit

import httpx

from app.domain.errors import ExternalServiceError, RuleViolationError

LINK_SECONDS = 300
"""Подписанная ссылка живёт 5 минут: хватает начать загрузку или открыть PDF, а пересланная
дальше ссылка к вечеру уже ничего не открывает."""


@dataclass(frozen=True, slots=True)
class UploadTarget:
    url: str
    method: str = "PUT"
    headers: dict[str, str] = field(default_factory=dict)


class FileStorage(Protocol):
    kind: str

    def upload_target(self, key: str, *, file_id: str, content_type: str) -> UploadTarget: ...

    def download_url(self, key: str, *, file_id: str) -> str: ...

    async def size(self, key: str) -> int | None:
        """Сколько байт лежит под ключом; `None` — ничего не лежит."""
        ...


class NoStorage:
    """Хранилище не настроено: загрузка честно отказывает."""

    kind = "none"

    def _refuse(self) -> RuleViolationError:
        return RuleViolationError(
            "Хранилище файлов не настроено",
            detail="Заказчик задаёт ключи хранилища в настройках рабочего контура (SETUP)",
        )

    def upload_target(self, key: str, *, file_id: str, content_type: str) -> UploadTarget:
        raise self._refuse()

    def download_url(self, key: str, *, file_id: str) -> str:
        raise self._refuse()

    async def size(self, key: str) -> int | None:
        return None


class LocalStorage:
    """Каталог на диске; содержимое принимает и отдаёт API (`/api/v1/files/{id}/content`)."""

    kind = "local"

    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, key: str) -> Path:
        target = (self.root / key).resolve()
        # Ключ строит сервер, но проверка дешевле уверенности: путь не выходит из корня.
        if self.root.resolve() not in target.parents:
            raise RuleViolationError("Недопустимый ключ файла")
        return target

    def upload_target(self, key: str, *, file_id: str, content_type: str) -> UploadTarget:
        return UploadTarget(
            url=f"/api/v1/files/{file_id}/content", headers={"Content-Type": content_type}
        )

    def download_url(self, key: str, *, file_id: str) -> str:
        return f"/api/v1/files/{file_id}/content"

    async def size(self, key: str) -> int | None:
        target = self.path(key)
        return target.stat().st_size if target.is_file() else None

    def write(self, key: str, content: bytes) -> None:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def presign(
    *,
    method: str,
    endpoint: str,
    bucket: str,
    key: str,
    region: str,
    access_key: str,
    secret_key: str,
    expires: int,
    now: datetime,
    path_style: bool = True,
) -> str:
    """Подписанная ссылка S3 (SigV4, подпись в строке запроса).

    Подписывается только заголовок `host`, тело — `UNSIGNED-PAYLOAD`: так ссылку можно
    отдать браузеру, и он отправит файл сам. Проверено на примере из документации AWS
    («Authenticating Requests: Using Query Parameters») — `tests/test_files.py`.
    """
    parts = urlsplit(endpoint)
    scheme = parts.scheme or "https"
    if path_style:
        host = parts.netloc
        path = f"/{bucket}/{quote(key, safe='/~')}"
    else:
        host = f"{bucket}.{parts.netloc}"
        path = f"/{quote(key, safe='/~')}"
    stamp = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    day = stamp[:8]
    scope = f"{day}/{region}/s3/aws4_request"
    query = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{access_key}/{scope}",
        "X-Amz-Date": stamp,
        "X-Amz-Expires": str(expires),
        "X-Amz-SignedHeaders": "host",
    }
    canonical_query = "&".join(
        f"{quote(name, safe='-_.~')}={quote(value, safe='-_.~')}"
        for name, value in sorted(query.items())
    )
    canonical_request = "\n".join(
        [method, path, canonical_query, f"host:{host}\n", "host", "UNSIGNED-PAYLOAD"]
    )
    to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            stamp,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signing = _sign(
        _sign(_sign(_sign(f"AWS4{secret_key}".encode(), day), region), "s3"), "aws4_request"
    )
    signature = hmac.new(signing, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{scheme}://{host}{path}?{canonical_query}&X-Amz-Signature={signature}"


class S3Storage:
    kind = "s3"

    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        region: str,
        access_key: str,
        secret_key: str,
        path_style: bool = True,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.bucket = bucket
        self.region = region
        self.access_key = access_key
        self.secret_key = secret_key
        self.path_style = path_style

    def _link(self, method: str, key: str) -> str:
        return presign(
            method=method,
            endpoint=self.endpoint,
            bucket=self.bucket,
            key=key,
            region=self.region,
            access_key=self.access_key,
            secret_key=self.secret_key,
            expires=LINK_SECONDS,
            now=datetime.now(UTC),
            path_style=self.path_style,
        )

    def upload_target(self, key: str, *, file_id: str, content_type: str) -> UploadTarget:
        return UploadTarget(url=self._link("PUT", key), headers={"Content-Type": content_type})

    def download_url(self, key: str, *, file_id: str) -> str:
        return self._link("GET", key)

    async def size(self, key: str) -> int | None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.head(self._link("HEAD", key))
        except httpx.HTTPError as error:
            raise ExternalServiceError("Хранилище файлов не ответило") from error
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise ExternalServiceError(f"Хранилище файлов ответило {response.status_code}")
        return int(response.headers.get("content-length", "0"))
