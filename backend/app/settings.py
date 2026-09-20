"""Настройки приложения.

Все значения приходят из окружения с префиксом `ORBITA_`. Значения по умолчанию совпадают
с docker-compose, чтобы после `make up` приложение поднималось без дополнительной
настройки. Обязательные параметры значения по умолчанию не имеют: приложение падает на
старте, а не работает вполсилы с пустым ключом.

Ключи объявлены типом `SecretStr` — он не печатается ни в логах, ни в отладочном выводе,
а репозиторий у нас публичный.

Строка подключения принимается двумя способами, и это не дублирование: в облаке площадка
выдаёт одну готовую строку (`ORBITA_DATABASE_URL`), а на машине разработчика удобнее
части. Приведением занимается одно место — `sqlalchemy_url`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from pydantic import SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

Environment = Literal["development", "test", "preview", "production"]

# RFC 7518, раздел 3.2: ключ HMAC-SHA256 должен быть не короче размера выхода хеша.
MIN_SECRET_LENGTH = 32

# Секрет расписания едет в заголовке HTTP, а туда пускают только латиницу (RFC 7230).
MIN_JOBS_SECRET_LENGTH = 16

# Параметры соединения, которые понимает libpq и не понимает asyncpg. Их место — в
# аргументах подключения, а не в строке: с ними asyncpg падает с невнятной ошибкой.
LIBPQ_ONLY_PARAMS = frozenset({"sslmode", "channel_binding", "options", "connect_timeout"})

SSL_REQUIRED_MODES = frozenset({"require", "verify-ca", "verify-full"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ORBITA_",
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Приложение ---
    env: Environment = "development"
    base_url: str = "http://localhost:5173"
    """Адрес, по которому открывается интерфейс. Из него собираются личные ссылки доступа."""

    commit: str = "dev"
    """Коммит выложенной сборки. Возвращается в `/api/health`, чтобы проверка после
    выкладки видела не «что-то ответило», а «ответил именно этот коммит»."""

    default_locale: str = "ru"
    timezone: str = "Asia/Tashkent"

    # --- Секреты ---
    session_secret: SecretStr
    """Подписывает cookie сессии и личные ссылки доступа (ADR-0029). Обязателен."""

    jobs_secret: SecretStr
    """Пропуск к `/internal/jobs/{name}`. Знает его только расписание (ADR-0035)."""

    session_days: int = 30
    """Срок cookie сессии. Продлевается при каждом входе по ссылке."""

    # --- База данных ---
    database_url: str | None = None
    """Готовая строка подключения. В облаке её выдаёт площадка; пусто — собираем из частей."""

    # 127.0.0.1, а не localhost: см. пояснение в .env.example — разница в подключении
    # тридцатикратная, и платит её каждое соединение, а не только тесты.
    db_host: str = "127.0.0.1"
    db_port: int = 55432
    db_name: str = "orbita"
    db_user: str = "orbita"
    db_password: SecretStr = SecretStr("orbita")
    db_schema: str = "orbita"

    # --- Пороги сигналов ---
    # Значения для первой установки. В рабочей системе пороги живут в справочнике и
    # меняются без выкладки: это данные, а не код (CLAUDE.md, «чего не делать»).
    warn_days: int = 3
    quiet_days: int = 14
    summary_at: str = "08:30"

    # --- Наблюдаемость ---
    log_level: str = "INFO"
    # В разработке читаемый вывод, в остальных случаях JSON для сбора логов.
    log_json: bool | None = None

    @field_validator("session_secret")
    @classmethod
    def _session_secret_is_long_enough(cls, value: SecretStr) -> SecretStr:
        """Короткий ключ ослабляет подпись (RFC 7518, раздел 3.2).

        Проверка на старте, а не предупреждение в логах: предупреждение о слабом ключе
        читают ровно один раз, а живёт такой ключ годами.
        """
        if len(value.get_secret_value()) < MIN_SECRET_LENGTH:
            raise ValueError(
                f"ORBITA_SESSION_SECRET короче {MIN_SECRET_LENGTH} символов. "
                'Сгенерируйте: python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return value

    @field_validator("jobs_secret")
    @classmethod
    def _jobs_secret_fits_a_header(cls, value: SecretStr) -> SecretStr:
        """Секрет расписания едет в заголовке HTTP и обязан быть латиницей.

        Кириллический секрет невозможно даже отправить: клиент откажется собирать
        заголовок, а сервер ответит отказом — и выглядеть это будет как «расписание не
        работает», без единого указания на причину. Проверка на старте дешевле.
        """
        secret = value.get_secret_value()
        if len(secret) < MIN_JOBS_SECRET_LENGTH:
            raise ValueError(
                f"ORBITA_JOBS_SECRET короче {MIN_JOBS_SECRET_LENGTH} символов. "
                'Сгенерируйте: python -c "import secrets; print(secrets.token_urlsafe(24))"'
            )
        if not secret.isascii():
            raise ValueError(
                "ORBITA_JOBS_SECRET содержит нелатинские символы: такой секрет нельзя "
                "передать заголовком HTTP. Сгенерируйте: "
                'python -c "import secrets; print(secrets.token_urlsafe(24))"'
            )
        return value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_url(self) -> str:
        """Строка подключения для SQLAlchemy — с драйвером asyncpg и без чужих параметров.

        Площадки выдают строку для libpq: `postgresql://…?sslmode=require`. Драйвер
        asyncpg такую строку не принимает, и ошибка при этом говорит не про параметр, а
        про неизвестный ключевой аргумент. Поэтому схема заменяется, а параметры libpq
        уходят в `connect_args`.
        """
        if not self.database_url:
            password = self.db_password.get_secret_value()
            return (
                f"postgresql+asyncpg://{self.db_user}:{password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )

        parts = urlsplit(self.database_url)
        scheme = "postgresql+asyncpg"
        query = [
            (key, value) for key, value in parse_qsl(parts.query) if key not in LIBPQ_ONLY_PARAMS
        ]
        return urlunsplit(
            (scheme, parts.netloc, parts.path, "&".join(f"{k}={v}" for k, v in query), "")
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def alembic_url(self) -> str:
        """То же подключение для Alembic. Отдельное имя, чтобы не искать по коду."""
        return self.sqlalchemy_url

    @property
    def connect_args(self) -> dict[str, Any]:
        """Аргументы подключения asyncpg.

        Две вещи, без которых облачная база работает неверно:

        1. **TLS.** Облачные базы требуют шифрования; в строке это `sslmode=require`,
           который asyncpg не понимает, — здесь он превращается в `ssl`.
        2. **Отключённый кеш подготовленных запросов** при подключении через пул
           соединений (у Neon это хост с суффиксом `-pooler`). Пул раздаёт одно
           соединение разным клиентам, и подготовленный запрос второго клиента приходит
           в чужой сеанс: ошибка «prepared statement does not exist» появляется под
           нагрузкой и не воспроизводится на машине разработчика.
        """
        args: dict[str, Any] = {
            "server_settings": {
                # Все таблицы живут в схеме orbita: так база делится с ассистентом SETA
                # без пересечения имён. Схему создаёт миграция, не приложение.
                "search_path": f"{self.db_schema},public",
                "application_name": "orbita",
            }
        }

        if self.database_url:
            parts = urlsplit(self.database_url)
            params = dict(parse_qsl(parts.query))
            if params.get("sslmode", "").lower() in SSL_REQUIRED_MODES:
                args["ssl"] = True
            if "-pooler" in (parts.hostname or ""):
                args["statement_cache_size"] = 0

        return args

    @computed_field  # type: ignore[prop-decorator]
    @property
    def use_json_logs(self) -> bool:
        if self.log_json is not None:
            return self.log_json
        return self.env != "development"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def debug(self) -> bool:
        return self.env == "development"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_real_data(self) -> bool:
        """Работаем ли мы с настоящими данными агентства.

        Отсюда растут запреты: сброс демо-данных в рабочем контуре не выполняется, а
        наполнение вымышленными данными в нём запрещено (CLAUDE.md, инвариант 11).
        """
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    """Настройки читаются один раз за процесс.

    Кеш сбрасывается в тестах через `get_settings.cache_clear()`, когда нужно проверить
    поведение при других переменных окружения.
    """
    return Settings()
