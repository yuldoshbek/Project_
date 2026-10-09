"""Файлы и версии презентаций — загрузка, просмотр, замечания на слайд (ADR-0009, ТЗ 3.5).

1. **Подпись S3** совпадает с примером из документации AWS — ссылку примет любое
   S3-совместимое хранилище.
2. **Загрузка в три шага**: ссылка → файл → проверка; версия видна только после проверки.
3. **Тип и размер** — белый список и предел; без хранилища — честный отказ.
4. **Замечание на слайд** — оба; «исправлено» — помощник, в последней версии.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app import demo
from app.adapters.storage import LocalStorage, NoStorage, presign
from app.domain.clock import now_utc
from app.repos.models import StoredFile

TASHKENT = ZoneInfo("Asia/Tashkent")
PDF = "application/pdf"


class TestPresign:
    def test_matches_the_aws_documentation_example(self) -> None:
        """«Authenticating Requests: Using Query Parameters (AWS Signature Version 4)»."""
        url = presign(
            method="GET",
            endpoint="https://s3.amazonaws.com",
            bucket="examplebucket",
            key="test.txt",
            region="us-east-1",
            access_key="AKIAIOSFODNN7EXAMPLE",
            secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            expires=86400,
            now=datetime(2013, 5, 24, tzinfo=UTC),
            path_style=False,
        )
        assert url.startswith("https://examplebucket.s3.amazonaws.com/test.txt?")
        assert url.endswith(
            "X-Amz-Signature=aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404"
        )

    def test_path_style_keeps_the_bucket_in_the_path(self) -> None:
        url = presign(
            method="PUT",
            endpoint="https://storage.example.uz",
            bucket="orbita",
            key="presentation_version/a/b.pdf",
            region="auto",
            access_key="key",
            secret_key="secret",
            expires=300,
            now=datetime(2026, 10, 5, tzinfo=UTC),
        )
        assert url.startswith("https://storage.example.uz/orbita/presentation_version/a/b.pdf?")
        assert "X-Amz-Expires=300" in url


@pytest.fixture
async def loaded(session: AsyncSession, app: FastAPI, tmp_path: Path) -> None:
    app.state.storage = LocalStorage(tmp_path)
    now = now_utc()
    await demo.before_visit(session, now=now, zone=TASHKENT)
    await demo.after_visit(session, now=now, zone=TASHKENT)


async def drought(api: AsyncClient) -> str:
    body = (await api.get("/api/v1/preparations")).json()
    found: str = next(
        each["id"]
        for each in body["items"]
        if each["title"] == "Об итогах космического мониторинга засухи"
    )
    return found


async def upload(api: AsyncClient, prep_id: str, content: bytes) -> dict[str, Any]:
    started = await api.post(
        f"/api/v1/preparations/{prep_id}/versions",
        json={"name": "Доклад о засухе.pdf", "content_type": PDF, "size": len(content)},
    )
    assert started.status_code == 201, started.text
    body: dict[str, Any] = started.json()
    assert body["upload"]["url"] == f"/api/v1/files/{body['file_id']}/content"
    put = await api.put(body["upload"]["url"], content=content, headers={"Content-Type": PDF})
    assert put.status_code == 204, put.text
    done = await api.post(f"/api/v1/files/{body['file_id']}/complete")
    assert done.status_code == 204, done.text
    return body


@pytest.mark.infra
@pytest.mark.usefixtures("loaded")
class TestVersions:
    async def test_upload_in_three_steps_and_open(self, assistant_api: AsyncClient) -> None:
        prep_id = await drought(assistant_api)
        content = b"%PDF-1.4 fictional presentation"

        started = await assistant_api.post(
            f"/api/v1/preparations/{prep_id}/versions",
            json={"name": "черновик.pdf", "content_type": PDF, "size": len(content)},
        )
        card = (await assistant_api.get(f"/api/v1/preparations/{prep_id}")).json()
        # Пока файл не проверен, версии в карточке нет: ссылка на пустое место не показывается.
        assert card["versions"] == []
        early = await assistant_api.post(f"/api/v1/files/{started.json()['file_id']}/complete")
        assert early.status_code == 422

        body = await upload(assistant_api, prep_id, content)
        card = (await assistant_api.get(f"/api/v1/preparations/{prep_id}")).json()
        assert [each["number"] for each in card["versions"]] == [2]
        assert card["versions"][0]["state"] == "review"
        assert card["versions"][0]["file"]["name"] == "Доклад о засухе.pdf"

        link = (await assistant_api.get(f"/api/v1/files/{body['file_id']}/link")).json()
        opened = await assistant_api.get(link["url"])
        assert opened.status_code == 200
        assert opened.content == content
        assert opened.headers["content-disposition"].startswith("inline")

    async def test_abandoned_upload_does_not_take_a_number(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Брошенная загрузка не оставляет дыры в номерах: «Версия 6», следом «Версия 8»."""
        prep_id = await drought(assistant_api)
        started = await assistant_api.post(
            f"/api/v1/preparations/{prep_id}/versions",
            json={"name": "брошено.pdf", "content_type": PDF, "size": 10},
        )
        abandoned = uuid.UUID(started.json()["file_id"])
        await session.execute(
            update(StoredFile)
            .where(StoredFile.id == abandoned)
            .values(created_at=now_utc() - timedelta(hours=2))
        )
        await upload(assistant_api, prep_id, b"%PDF next")
        card = (await assistant_api.get(f"/api/v1/preparations/{prep_id}")).json()
        assert [each["number"] for each in card["versions"]] == [1]
        assert await session.get(StoredFile, abandoned) is None

    async def test_landed_but_unconfirmed_upload_is_kept(
        self, assistant_api: AsyncClient, session: AsyncSession
    ) -> None:
        """Файл лёг, а подтверждение не дошло: загрузка завершается при следующей, а не
        удаляется (файл стал бы сиротой) и не висит невидимой версией с дырой в номерах."""
        prep_id = await drought(assistant_api)
        started = (
            await assistant_api.post(
                f"/api/v1/preparations/{prep_id}/versions",
                json={"name": "лёг.pdf", "content_type": PDF, "size": 9},
            )
        ).json()
        put = await assistant_api.put(
            started["upload"]["url"], content=b"%PDF lost", headers={"Content-Type": PDF}
        )
        assert put.status_code == 204
        landed = uuid.UUID(started["file_id"])
        await session.execute(
            update(StoredFile)
            .where(StoredFile.id == landed)
            .values(created_at=now_utc() - timedelta(hours=2))
        )
        await upload(assistant_api, prep_id, b"%PDF next")
        card = (await assistant_api.get(f"/api/v1/preparations/{prep_id}")).json()
        assert sorted(each["number"] for each in card["versions"]) == [1, 2]

    async def test_type_size_and_role_are_checked(
        self, assistant_api: AsyncClient, leader_api: AsyncClient
    ) -> None:
        prep_id = await drought(assistant_api)
        path = f"/api/v1/preparations/{prep_id}/versions"
        exe = {"name": "x.exe", "content_type": "application/x-msdownload", "size": 10}
        assert (await assistant_api.post(path, json=exe)).status_code == 422
        huge = {"name": "x.pdf", "content_type": PDF, "size": 60 * 1024 * 1024}
        assert (await assistant_api.post(path, json=huge)).status_code == 422
        good = {"name": "x.pdf", "content_type": PDF, "size": 10}
        assert (await leader_api.post(path, json=good)).status_code == 403

    async def test_size_mismatch_is_refused(self, assistant_api: AsyncClient) -> None:
        prep_id = await drought(assistant_api)
        started = (
            await assistant_api.post(
                f"/api/v1/preparations/{prep_id}/versions",
                json={"name": "x.pdf", "content_type": PDF, "size": 100},
            )
        ).json()
        put = await assistant_api.put(started["upload"]["url"], content=b"short")
        assert put.status_code == 422

    async def test_comments_and_fixes(
        self, assistant_api: AsyncClient, leader_api: AsyncClient
    ) -> None:
        prep_id = await drought(assistant_api)
        first = await upload(assistant_api, prep_id, b"%PDF first")
        comment = await leader_api.post(
            f"/api/v1/preparations/{prep_id}/versions/{first['version_id']}/comments",
            json={"slide": 3, "text": "Карта без легенды"},
        )
        assert comment.status_code == 201, comment.text
        state = await leader_api.put(
            f"/api/v1/preparations/{prep_id}/versions/{first['version_id']}/state",
            json={"state": "rework", "version": 1},
        )
        assert state.status_code == 204

        await upload(assistant_api, prep_id, b"%PDF second")
        card = (await assistant_api.get(f"/api/v1/preparations/{prep_id}")).json()
        old = next(each for each in card["versions"] if each["id"] == first["version_id"])
        assert old["state"] == "rework"
        remark = old["comments"][0]
        assert (remark["slide"], remark["author"], remark["fixed_in"]) == (3, "leader", None)

        fixed = await assistant_api.put(
            f"/api/v1/preparations/{prep_id}/comments/{remark['id']}/fixed",
            json={"fixed": True, "version": remark["version"]},
        )
        assert fixed.status_code == 204
        card = (await assistant_api.get(f"/api/v1/preparations/{prep_id}")).json()
        old = next(each for each in card["versions"] if each["id"] == first["version_id"])
        assert old["comments"][0]["fixed_in"] == card["versions"][0]["number"]


@pytest.mark.infra
@pytest.mark.usefixtures("loaded")
class TestMovedWithoutFiles:
    async def test_missing_file_is_an_honest_not_found(
        self, app: FastAPI, assistant_api: AsyncClient, tmp_path: Path
    ) -> None:
        """База переехала, а каталог файлов — нет: отказ словами, а не 500."""
        prep_id = await drought(assistant_api)
        body = await upload(assistant_api, prep_id, b"%PDF moved")
        app.state.storage = LocalStorage(tmp_path / "other-disk")
        link = (await assistant_api.get(f"/api/v1/files/{body['file_id']}/link")).json()
        opened = await assistant_api.get(link["url"])
        assert opened.status_code == 404
        assert "не перенесли" in opened.text


@pytest.mark.infra
class TestWithoutStorage:
    async def test_upload_is_refused_honestly(
        self, app: FastAPI, session: AsyncSession, assistant_api: AsyncClient
    ) -> None:
        app.state.storage = NoStorage()
        now = now_utc()
        await demo.before_visit(session, now=now, zone=TASHKENT)
        prep_id = await drought(assistant_api)
        response = await assistant_api.post(
            f"/api/v1/preparations/{prep_id}/versions",
            json={"name": "x.pdf", "content_type": PDF, "size": 10},
        )
        assert response.status_code == 422
        assert "не настроено" in response.text
        card = (await assistant_api.get(f"/api/v1/preparations/{prep_id}")).json()
        assert card["versions"] == []


def test_links_expire() -> None:
    url = presign(
        method="GET",
        endpoint="https://s.example",
        bucket="b",
        key="k",
        region="auto",
        access_key="a",
        secret_key="s",
        expires=300,
        now=datetime.now(UTC) - timedelta(minutes=1),
    )
    assert "X-Amz-Expires=300" in url


JPEG = "image/jpeg"


async def a_task(api: AsyncClient) -> str:
    items = (await api.get("/api/v1/tasks")).json()["items"]
    task_id: str = items[0]["id"]
    return task_id


@pytest.mark.infra
@pytest.mark.usefixtures("loaded")
class TestPhotos:
    """Фото из Захвата (ТЗ 7, V18): к записи, которую Захват завёл, тем же путём загрузки."""

    async def test_leader_attaches_a_photo_and_the_card_shows_it(
        self, leader_api: AsyncClient
    ) -> None:
        """Руководитель записывает с телефона — и фото кладёт он сам, не помощник."""
        task_id = await a_task(leader_api)
        content = b"\xff\xd8\xff fictional photo"
        started = await leader_api.post(
            "/api/v1/files/photos",
            json={
                "owner_type": "task",
                "owner_id": task_id,
                "name": "доска.jpg",
                "content_type": JPEG,
                "size": len(content),
            },
        )
        assert started.status_code == 201, started.text
        body = started.json()
        listing = {"owner_type": "task", "owner_id": task_id}
        # Пока фото не проверено, в карточке его нет.
        assert (await leader_api.get("/api/v1/files/photos", params=listing)).json() == []

        put = await leader_api.put(
            body["upload"]["url"], content=content, headers={"Content-Type": JPEG}
        )
        assert put.status_code == 204, put.text
        done = await leader_api.post(f"/api/v1/files/{body['file_id']}/complete")
        assert done.status_code == 204, done.text

        photos = (await leader_api.get("/api/v1/files/photos", params=listing)).json()
        assert [photo["name"] for photo in photos] == ["доска.jpg"]
        link = (await leader_api.get(f"/api/v1/files/{photos[0]['id']}/link")).json()
        assert (await leader_api.get(link["url"])).content == content

    async def test_only_images_to_known_records(self, assistant_api: AsyncClient) -> None:
        task_id = await a_task(assistant_api)
        base = {"owner_type": "task", "owner_id": task_id, "name": "x", "size": 10}
        pdf = {**base, "content_type": PDF}
        assert (await assistant_api.post("/api/v1/files/photos", json=pdf)).status_code == 422
        missing = {**base, "content_type": JPEG, "owner_id": str(uuid.uuid4())}
        assert (await assistant_api.post("/api/v1/files/photos", json=missing)).status_code == 404
        version = {**base, "content_type": JPEG, "owner_type": "presentation_version"}
        assert (await assistant_api.post("/api/v1/files/photos", json=version)).status_code == 422

    async def test_presentation_stays_the_assistants_file(
        self, assistant_api: AsyncClient, leader_api: AsyncClient
    ) -> None:
        """Фото кладут оба, а версию презентации по-прежнему подтверждает только помощник."""
        prep_id = await drought(assistant_api)
        started = (
            await assistant_api.post(
                f"/api/v1/preparations/{prep_id}/versions",
                json={"name": "x.pdf", "content_type": PDF, "size": 10},
            )
        ).json()
        refused = await leader_api.post(f"/api/v1/files/{started['file_id']}/complete")
        assert refused.status_code == 403

    async def test_idea_photos_come_with_the_ideas_list(self, leader_api: AsyncClient) -> None:
        """У идеи нет карточки — карточка и есть строка: фото приходят вместе со списком."""
        saved = (
            await leader_api.post(
                "/api/v1/captures", json={"kind": "idea", "text": "Спутник для лесхозов"}
            )
        ).json()
        owner = saved["photo_owner"]
        assert owner["owner_type"] == "idea"
        content = b"\xff\xd8\xff idea photo"
        started = (
            await leader_api.post(
                "/api/v1/files/photos",
                json={**owner, "name": "эскиз.jpg", "content_type": JPEG, "size": len(content)},
            )
        ).json()
        await leader_api.put(started["upload"]["url"], content=content)
        await leader_api.post(f"/api/v1/files/{started['file_id']}/complete")

        items = (await leader_api.get("/api/v1/ideas")).json()["items"]
        idea = next(item for item in items if item["id"] == owner["owner_id"])
        assert [photo["name"] for photo in idea["photos"]] == ["эскиз.jpg"]
        others = [item for item in items if item["id"] != owner["owner_id"]]
        assert all(item["photos"] == [] for item in others)
