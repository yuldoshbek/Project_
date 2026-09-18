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

from pydantic import SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.documents import DEFAULT_MAX_UPLOAD_MB, MEGABYTE

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

Environment = Literal["development", "test", "production"]

# RFC 7518, раздел 3.2: ключ HMAC-SHA256 должен быть не короче размера выхода хеша.
MIN_SECRET_KEY_LENGTH = 32


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

    # --- Кто может звать API из браузера (ADR-0026) ---
    # Входа в системе нет, и единственное, что отделяет её от чужого браузера, — этот
    # список и периметр. Значения через запятую: адрес фронтенда на сервере агентства,
    # адрес сборки на Netlify, адрес разработки.
    #
    # Параметр, а не константа: домен выкладки меняется без правки кода. Пустая строка
    # означает «чужим источникам нельзя» — так и должно быть, пока домен неизвестен.
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # --- Redis ---
    redis_url: str = "redis://127.0.0.1:56379/0"

    # --- Хранилище файлов (ADR-0009) ---
    s3_endpoint: str = "http://127.0.0.1:59000"
    s3_bucket: str = "orbita"
    s3_access_key: SecretStr = SecretStr("orbita")
    s3_secret_key: SecretStr = SecretStr("orbita-secret")
    # MinIO область не использует, но подпись запроса её требует. Имя значения не имеет
    # и должно лишь совпадать у того, кто подписывает, и у того, кто проверяет.
    s3_region: str = "us-east-1"
    # Первый уровень ключа. Отделяет наши файлы от чужих, если бакет однажды окажется
    # общим с ассистентом SETA (ADR-0001).
    s3_prefix: str = "orbita"

    # --- Вложения ---
    max_upload_mb: int = DEFAULT_MAX_UPLOAD_MB
    # Время жизни ссылки на файл. Пять минут: столько нужно, чтобы браузер успел начать
    # скачивание большого файла, и слишком мало, чтобы ссылка пережила пересылку.
    # Срок один для всех файлов. Второго значения — минуты для проекта с грифом — больше
    # нет: гриф снят, а ссылку получают те же двое, и пересылать её некому
    # (ADR-0024).
    download_link_seconds: int = 300

    # --- Антивирус (Q7) ---
    # clamav — проверять, disabled — не проверять. Второе значение существует ради
    # тестов и разработки без поднятого окружения; на рабочем контуре оно означает, что
    # требование СБ не выполняется, и это видно по одной строке настроек.
    antivirus: str = "clamav"
    antivirus_host: str = "127.0.0.1"
    antivirus_port: int = 53310
    # Проверка идёт в запросе на загрузку: пятьдесят мегабайт clamd просматривает
    # секунды. Больше минуты — это не «медленно», а «не отвечает».
    antivirus_timeout_seconds: float = 60.0

    # --- Предпросмотр офисных форматов (ADR-0009) ---
    # gotenberg — LibreOffice в отдельном контейнере за HTTP; disabled — не строить
    # производный PDF.
    preview_converter: str = "gotenberg"
    preview_url: str = "http://127.0.0.1:53000"
    preview_timeout_seconds: float = 120.0

    # --- Наблюдаемость ---
    log_level: str = "INFO"
    # В разработке читаемый вывод, в остальных случаях JSON для сбора логов.
    log_json: bool | None = None

    @field_validator("secret_key")
    @classmethod
    def _secret_key_is_long_enough(cls, value: SecretStr) -> SecretStr:
        """Ключ короче 32 байт ослабляет подпись токенов (RFC 7518, раздел 3.2).

        Проверка на старте, а не предупреждение в логах: предупреждение о слабом
        ключе читают ровно один раз, а живёт такой ключ годами.
        Сгенерировать: python -c "import secrets; print(secrets.token_urlsafe(48))"
        """
        if len(value.get_secret_value()) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(
                f"ORBITA_SECRET_KEY короче {MIN_SECRET_KEY_LENGTH} символов. "
                'Сгенерируйте: python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        return value

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
    def upload_max_bytes(self) -> int:
        """Предел вложения в байтах. В настройках он в мегабайтах — так его читают люди."""
        return self.max_upload_mb * MEGABYTE

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
