"""Настройки приложения.

Все значения приходят из окружения с префиксом `ORBITA_`. Значения по умолчанию
совпадают с docker-compose, чтобы после `make up` приложение поднималось без
дополнительной настройки.

Обязательные параметры не имеют значения по умолчанию: приложение падает на старте, а не
работает вполсилы с пустым ключом. Ключи и секреты объявлены типом `SecretStr` — он не
печатается в логах и в отладочном выводе, а репозиторий у нас публичный.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

Environment = Literal["development", "test", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ORBITA_",
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Приложение ---
    env: Environment = "development"
    # Обязателен: без него приложение не стартует. Так и задумано.
    secret_key: SecretStr
    base_url: str = "http://localhost:5173"
    default_locale: str = "ru"
    timezone: str = "Asia/Tashkent"

    # --- База данных ---
    # 127.0.0.1, а не localhost: см. пояснение в .env.example — разница в подключении
    # тридцатикратная, и платит её каждое соединение, а не только тесты.
    db_host: str = "127.0.0.1"
    db_port: int = 55432
    db_name: str = "orbita"
    db_user: str = "orbita"
    db_password: SecretStr = SecretStr("orbita")
    db_schema: str = "orbita"

    # --- Redis ---
    redis_url: str = "redis://127.0.0.1:56379/0"

    # --- Наблюдаемость ---
    log_level: str = "INFO"
    # В разработке читаемый вывод, в остальных случаях JSON для сбора логов.
    log_json: bool | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """DSN для SQLAlchemy. Пароль подставляется из SecretStr в момент подключения."""
        password = self.db_password.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.db_user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

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


@lru_cache
def get_settings() -> Settings:
    """Настройки читаются один раз за процесс.

    Кеш сбрасывается в тестах через `get_settings.cache_clear()`, когда нужно проверить
    поведение при других переменных окружения.
    """
    return Settings()
