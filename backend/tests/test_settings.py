"""Настройки: обязательные значения, сборка строки подключения, выбор формата логов."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from app.settings import MIN_SECRET_LENGTH, Settings

LONG_ENOUGH_KEY = "к" * MIN_SECRET_LENGTH


def build(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "env": "test",
        "session_secret": SecretStr(LONG_ENOUGH_KEY),
        "jobs_secret": SecretStr("jobs-secret-for-tests"),
        # Окружение прогона несёт .env разработчика: без явного None часть проверок
        # читала бы его строку подключения вместо своей.
        "database_url": None,
        "_env_file": None,
    }
    return Settings(**{**defaults, **overrides})  # type: ignore[arg-type]


def test_secrets_are_required(monkeypatch: pytest.MonkeyPatch) -> None:
    """Без ключей приложение обязано упасть на старте, а не работать вполсилы."""
    monkeypatch.delenv("ORBITA_SESSION_SECRET", raising=False)
    monkeypatch.delenv("ORBITA_JOBS_SECRET", raising=False)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    assert "session_secret" in str(error.value)
    assert "jobs_secret" in str(error.value)


def test_connection_string_is_built_from_parts() -> None:
    """На машине разработчика удобнее части, и из них собирается адрес для asyncpg."""
    settings = build(
        db_host="db.example",
        db_port=5432,
        db_name="orbita",
        db_user="orbita",
        db_password=SecretStr("p@ss"),
    )

    assert settings.sqlalchemy_url == "postgresql+asyncpg://orbita:p@ss@db.example:5432/orbita"


def test_ready_connection_string_wins_over_parts() -> None:
    """В облаке площадка выдаёт готовую строку, и части при этом ни при чём."""
    settings = build(
        database_url="postgresql://cloud:pwd@ep-quiet-1.eu-central-1.aws.neon.tech/orbita",
        db_host="127.0.0.1",
    )

    assert settings.sqlalchemy_url.startswith("postgresql+asyncpg://cloud:pwd@ep-quiet-1")
    assert "127.0.0.1" not in settings.sqlalchemy_url


def test_libpq_parameters_move_out_of_the_url() -> None:
    """`sslmode` в строке — обычный вид облачного адреса, и asyncpg его не принимает.

    Ошибка при этом говорит не про параметр, а про неизвестный аргумент, и на выкладке
    выглядит как поломка приложения. Поэтому параметр уходит в аргументы подключения.
    """
    settings = build(
        database_url=(
            "postgresql://u:p@ep-quiet-1.eu-central-1.aws.neon.tech/orbita"
            "?sslmode=require&channel_binding=require"
        )
    )

    assert "sslmode" not in settings.sqlalchemy_url
    assert "channel_binding" not in settings.sqlalchemy_url
    assert settings.connect_args["ssl"] is True


def test_pooled_connection_disables_statement_cache() -> None:
    """За пулом соединений подготовленный запрос уходит в чужой сеанс.

    Ошибка «prepared statement does not exist» появляется под нагрузкой и не
    воспроизводится на машине разработчика — поэтому кеш отключается по виду адреса.
    """
    settings = build(
        database_url="postgresql://u:p@ep-quiet-1-pooler.eu-central-1.aws.neon.tech/orbita"
    )

    assert settings.connect_args["statement_cache_size"] == 0


def test_direct_connection_keeps_statement_cache() -> None:
    settings = build(database_url="postgresql://u:p@ep-quiet-1.eu-central-1.aws.neon.tech/orbita")

    assert "statement_cache_size" not in settings.connect_args


def test_schema_is_set_on_every_connection() -> None:
    """Таблицы живут в схеме orbita: без search_path приложение смотрит в public."""
    assert build().connect_args["server_settings"]["search_path"] == "orbita,public"


def test_secrets_are_not_printed() -> None:
    """Репозиторий публичный, логи попадают в отчёты — секрет не должен светиться."""
    secret = "очень-секретно-и-достаточно-длинно-для-подписи"
    settings = build(session_secret=SecretStr(secret))

    assert secret not in repr(settings)
    assert secret not in str(settings)


def test_short_session_secret_stops_the_application() -> None:
    """Ключ короче 32 символов ослабляет подпись (RFC 7518, раздел 3.2).

    Падение на старте, а не предупреждение в логах: предупреждение читают один раз,
    а слабый ключ живёт годами.
    """
    with pytest.raises(ValidationError) as error:
        build(session_secret=SecretStr("коротко"))

    assert "32" in str(error.value)


def test_jobs_secret_must_fit_an_http_header() -> None:
    """Кириллический секрет расписания нельзя даже отправить заголовком.

    Без проверки это выглядело бы как «расписание не работает»: клиент отказывается
    собирать заголовок, сервер отвечает отказом, причины не видно нигде.
    """
    with pytest.raises(ValidationError) as error:
        build(jobs_secret=SecretStr("секрет-по-русски"))

    assert "нелатинские" in str(error.value)


def test_short_jobs_secret_is_refused() -> None:
    with pytest.raises(ValidationError):
        build(jobs_secret=SecretStr("коротко"))


def test_console_logs_in_development_json_elsewhere() -> None:
    assert build(env="development").use_json_logs is False
    assert build(env="production").use_json_logs is True
    assert build(env="test").use_json_logs is True


def test_log_format_can_be_forced() -> None:
    assert build(env="development", log_json=True).use_json_logs is True
    assert build(env="production", log_json=False).use_json_logs is False


def test_real_data_only_in_production() -> None:
    """Признак, на который опираются запреты: демо-данные и сброс — не в рабочем контуре."""
    assert build(env="production").is_real_data is True
    assert build(env="preview").is_real_data is False
    assert build(env="development").is_real_data is False


def test_unknown_variables_are_ignored() -> None:
    """Окружение общее с ассистентом SETA: чужие переменные не должны ронять старт."""
    settings = build(some_unknown_variable="значение")

    assert settings.env == "test"
