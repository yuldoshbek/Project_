"""Хранилище в памяти процесса — для тестов.

Не «заглушка, которая ничего не делает»: она хранит содержимое и отдаёт его обратно,
поэтому тест на повторную загрузку, на удаление и на производный PDF проверяет
поведение, а не факт вызова. Подделка, которая всё принимает и ничего не помнит,
проходит любой тест — и ровно поэтому ничего не доказывает.

Ссылка выдаётся ненастоящая, но по правилам настоящей: со сроком жизни в запросе и с
именем файла. Тест «ссылка живёт ограниченное время» обязан проверять срок, а не наличие
строки.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from urllib.parse import urlencode

from app.adapters.storage import StorageError


class InMemoryStorage:
    """Хранилище, живущее ровно столько, сколько объект."""

    name = "memory"

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        # Сколько раз выдавалась ссылка — по этому проверяется, что содержимое наружу
        # уходит ссылкой, а не через приложение.
        self.links: list[str] = []

    async def put(self, key: str, data: bytes, *, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    async def get(self, key: str) -> bytes:
        if key not in self.objects:
            raise StorageError(f"нет объекта {key!r}")
        return self.objects[key][0]

    async def delete(self, keys: Sequence[str]) -> None:
        for key in keys:
            self.objects.pop(key, None)

    async def link(
        self,
        key: str,
        *,
        filename: str,
        content_type: str,
        inline: bool,
        lifetime: timedelta,
    ) -> str:
        if key not in self.objects:
            raise StorageError(f"нет объекта {key!r}")
        self.links.append(key)
        query = urlencode(
            {
                "expires": int(lifetime.total_seconds()),
                "filename": filename,
                "disposition": "inline" if inline else "attachment",
            }
        )
        return f"memory://{key}?{query}"
