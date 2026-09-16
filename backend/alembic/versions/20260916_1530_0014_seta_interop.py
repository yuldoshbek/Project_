"""Развязка с SETA: 64-битный Telegram, сопоставление сотрудников, проверка локали

Три правки, у которых одна причина — договор с SETA
([docs/integration/SETA-ORBITA.md](../../../docs/integration/SETA-ORBITA.md)). Две
системы переезжают на один сервер и начинают обмениваться записями, и там, где
раньше расхождение типов было безобидным, оно становится отказом при вставке.

`users.telegram_id` был создан `integer` (миграция 0003, строка 60), хотя
[SPEC.md](../../../docs/SPEC.md) требует `bigint` с самого начала. Telegram выдаёт
64-битные идентификаторы с 2021 года: на настоящем получателе вставка падала бы
переполнением, а не предупреждением. Модель объявляла тип неявно — `Mapped[int]`
означает `Integer`, — поэтому расхождение не поймал ни один тест: и база, и код
ошибались одинаково. Уникальное ограничение трогать не нужно, PostgreSQL
перестраивает индекс сам.

`people.external_seta_id` — сопоставление сотрудника агентства с человеком в SETA.
У `users` такое поле есть с первой миграции, у `people` не было: пока ORBITA ничего
не принимала снаружи, сопоставлять было не с чем. Договор приносит гостей,
участников встреч и исполнителей поручений — их надо узнавать между прогонами, а
не заводить заново каждый раз.

`ck_users_locale_is_known` — проверка кода локали. У нас коды по BCP 47
(`ru`, `uz-Cyrl`, `uz-Latn`), у SETA свои (`uz`, `uz_cyrl`, `ru`, `en`).
Соответствие переводится в шлюзе обмена, но до сих пор ничто не мешало записать
чужой код напрямую: колонка была `varchar(10)` без ограничения. Записанный `uz`
не сломал бы ничего в базе и молча сломал бы подбор словаря на экране — отказ,
который ищут глазами, а не по журналу.

Ревизия: 0014_seta_interop
Предыдущая: 0013_attachments_and_versions
Создана: 2026-09-16 15:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_seta_interop"
down_revision: str | None = "0013_attachments_and_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KNOWN_LOCALES = ("ru", "uz-Cyrl", "uz-Latn")


def upgrade() -> None:
    op.alter_column(
        "users",
        "telegram_id",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )

    op.add_column("people", sa.Column("external_seta_id", sa.String(length=100), nullable=True))
    op.create_unique_constraint(
        op.f("uq_people_external_seta_id"), "people", ["external_seta_id"]
    )

    values = ", ".join(f"'{code}'" for code in KNOWN_LOCALES)
    op.create_check_constraint(
        op.f("ck_users_locale_is_known"), "users", f"locale IN ({values})"
    )


def downgrade() -> None:
    # Откат обязан работать: миграция без проверенного отката — это миграция,
    # которую нельзя применить в рабочем контуре.
    op.drop_constraint(op.f("ck_users_locale_is_known"), "users", type_="check")

    op.drop_constraint(op.f("uq_people_external_seta_id"), "people", type_="unique")
    op.drop_column("people", "external_seta_id")

    # Сужение обратно в integer небезопасно при настоящих идентификаторах, поэтому
    # откат обрезает их явно, а не падает посреди ALTER: восстановить значения
    # всё равно неоткуда, и тихая потеря хуже громкой.
    op.execute("UPDATE users SET telegram_id = NULL WHERE telegram_id > 2147483647")
    op.alter_column(
        "users",
        "telegram_id",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
    )
