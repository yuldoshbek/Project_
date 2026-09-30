"""Уведомления на телефон руководителя: чистые правила (ТЗ 8, допущения V24–V29).

Поводов два, и оба названы в ТЗ: утренняя сводка («что ждёт решения и что горит сегодня»)
и вопрос помощника — «ждёт вашего решения». Получатель один — руководитель (V28): помощник
вносит вопрос сам и знать о нём пушем ему незачем.

Здесь то, что не зависит ни от базы, ни от сети: кто может подписаться, какую подписку
принять, как называется устройство, что лежит в пуше и когда сводке пора. Отправка —
`app.adapters.push`, запись и доставка — `app.services.notifications`.

**Текста для человека пуш не несёт** — только данные; фразу собирает сервис-воркер теми же
функциями, что и предпросмотр на вкладке «Сводка»
([ADR-0036](../../../docs/adr/ADR-0036-web-push.md)).
"""

from __future__ import annotations

import base64
import binascii
import uuid
from dataclasses import dataclass
from datetime import date, time
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

from app.domain.errors import PermissionDeniedError, RuleViolationError
from app.domain.people import Role

LAST_SUMMARY_RUN = time(11, 50)
"""Последний вызов расписания за утро по Ташкенту: `'*/10 1-6 * * *'` в
`.github/workflows/jobs.yml` зовёт сводку каждые десять минут с 06:00 до 11:50. Совпадение
с cron держит тест (`tests/test_jobs.py`); экран обещает повтор «до» этого времени
(`GET /api/v1/pult/summary`, поле `last_run`)."""

SUMMARY_WINDOW = (time(6, 0), time(11, 0))
"""Какое время сводки принимает порог (`app.domain.management.clean_threshold`).

Конец окна — на пятьдесят минут раньше последнего вызова, а не вровень с ним: GitHub
пропускает запуски по расписанию под нагрузкой, и служба уведомлений отказывает на
минуты. Сводке в 11:50 досталась бы одна попытка, и один пропуск оставлял руководителя
без сводки до завтра; в 11:00 попыток шесть. Время раньше начала окна не наступило бы
вовсе — первый вызов в 06:00."""

PUSH_FIELD_LENGTH = 150
"""Сколько символов названия и подписи строки едет в пуше. Экран блокировки показывает две
строки по одной-две строчки, а служба уведомлений принимает не больше 4 КБ
зашифрованного содержимого: решение длиной в тысячу кириллических символов — уже 2 КБ, и
сводка из двух таких строк не прошла бы ни разу. С полями по 150 символов самая длинная
сводка — 1544 байта при пределе 3993 (`tests/test_push_domain.py`)."""

SUMMARY_URL = "/?view=summary"
"""Куда ведёт касание пуша: вкладка «Сводка» Пульта. Вопрос ведёт туда же — там видно, что
ждёт решения, и там же его принимают (V27)."""

QUESTION_PREVIEW_LENGTH = 300
"""Сколько символов вопроса едет в пуше: вопрос — главное в этом уведомлении, и места ему
вдвое больше, чем названию (`PUSH_FIELD_LENGTH`). Вопрос в тысячу кириллических символов
занял бы 2 КБ из 4 КБ, которые принимает служба."""

ENDPOINT_MAX_LENGTH = 1000
"""Как столбец `push_subscriptions.endpoint`. Адреса служб — 150–400 символов."""

P256DH_BYTES = 65
"""Открытый ключ браузера — точка P-256 в несжатом виде: байт 0x04 и две координаты."""

AUTH_BYTES = 16
"""Секрет подписки для шифрования содержимого (RFC 8291, раздел 3.2)."""

PUSH_SERVICES = (
    "push.apple.com",
    "fcm.googleapis.com",
    "push.services.mozilla.com",
    "notify.windows.com",
)
"""Службы уведомлений браузеров: Safari на iPhone и Mac, Chrome и Edge на Android, Firefox,
Edge на Windows. Сервер сам отправляет POST по адресу подписки, и без этого списка
подписка стала бы способом заставить его постучаться куда угодно, включая внутреннюю сеть
площадки."""

UNKNOWN_DEVICE = "устройство"
"""Название устройства, которое не удалось узнать по заголовку браузера."""

# Порядок важен: у Android в заголовке есть «Linux», у iPhone — «like Mac OS X».
_DEVICES = (
    ("iPhone", "iPhone"),
    ("iPad", "iPad"),
    ("Android", "Android"),
    ("Macintosh", "Mac"),
    ("Windows", "Windows"),
    ("Linux", "Linux"),
)


class NotificationKind(StrEnum):
    """Повод уведомления — два, по ТЗ 8."""

    MORNING_SUMMARY = "morning_summary"
    AWAITING_DECISION = "awaiting_decision"

    @property
    def ttl(self) -> int:
        """Сколько секунд служба держит пуш для выключенного телефона.

        Сводка через двенадцать часов уже вечерняя, а утром придёт новая. Вопрос живёт
        сутки: не доставленный за сутки, он и так будет в следующей утренней сводке.
        """
        return 43200 if self is NotificationKind.MORNING_SUMMARY else 86400

    @property
    def urgency(self) -> str:
        """Срочность для службы (RFC 8030, раздел 5.3).

        Вопрос будит телефон сразу — ради этого пуш и отправляется в момент вопроса (V27).
        Сводке спешить некуда: служба может придержать её до пробуждения телефона и
        сберечь батарею.
        """
        return "normal" if self is NotificationKind.MORNING_SUMMARY else "high"


class SummaryOutcome(StrEnum):
    """Почему сводка ушла или не ушла — это видно в сводке прогона расписания.

    День занимает только `sent`: сводка доставлена хотя бы на одно устройство. Остальное
    оставляет день свободным, и следующий вызов расписания пробует снова: руководитель,
    включивший уведомления в 09:00, получает сводку в 09:10, а не завтра.
    """

    SENT = "sent"
    NOT_YET = "not_yet"
    """Назначенное время ещё не наступило."""
    NO_DEVICE = "no_device"
    """Руководитель не включил уведомления ни на одном устройстве или все они отключены."""
    NOT_CONFIGURED = "not_configured"
    """У сервера нет ключа уведомлений — его вводит заказчик."""
    REFUSED = "refused"
    """Служба уведомлений не приняла сводку ни для одного устройства."""


@dataclass(frozen=True, slots=True)
class Subscription:
    """Подписка браузера в том виде, в каком её можно хранить и по ней отправлять."""

    endpoint: str
    p256dh: str
    auth: str


def check_subscriber(role: Role) -> None:
    """Подписывается только руководитель (V28).

    Третье исключение из «данные вносит помощник» — после решения руководителя и его
    записей в Захвате (`app.api.security.require_assistant`): подписка — это его телефон,
    и включить уведомления за него нельзя.
    """
    if role is not Role.LEADER:
        raise PermissionDeniedError(
            "Сводку и пуши получает руководитель: уведомления включаются на его устройстве"
        )


def decode_key(value: str) -> bytes:
    """Ключ подписки из base64url — в том виде, в каком его отдаёт `PushSubscription.toJSON()`.

    Строгий разбор: посторонний символ — отказ, а не молча выброшенный байт, как делает
    `base64.urlsafe_b64decode`. Иначе повреждённый ключ прошёл бы проверку длины случайно и
    упал бы на первой отправке, утром, без следа причины.
    """
    try:
        return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as error:
        raise RuleViolationError("Ключ подписки повреждён: включите уведомления заново") from error


def clean_subscription(*, endpoint: str, p256dh: str, auth: str) -> Subscription:
    """Подписка, которую можно принять: адрес службы уведомлений и годные ключи.

    Адрес разбирается дважды: `urlsplit` — чтобы увидеть хост, httpx — тем же разбором,
    которым его потом отправят. Адрес, принятый здесь и отвергнутый httpx на отправке
    (порт из букв, мягкий перенос в имени хоста), каждое утро давал бы неудачную отправку
    вместо честного отказа в момент подписки.
    """
    import httpx  # здесь, а не наверху: при старте httpx не нужен (`app.adapters.push`)

    not_a_service = RuleViolationError(
        "Адрес подписки не похож на адрес службы уведомлений: включите уведомления заново"
    )
    address = endpoint.strip()
    try:
        parts = urlsplit(address)
        # Порт и имя хоста разбираются лениво: `port` бросает на значении вне 0–65535,
        # `host` — на испорченном punycode (`xn--zz`). Без этих чтений такой адрес прошёл бы
        # проверку и отказал только при отправке.
        port = parts.port
        httpx.URL(address).host  # noqa: B018 — чтение ради проверки
    except (ValueError, httpx.InvalidURL) as error:
        raise not_a_service from error
    if (
        len(address) > ENDPOINT_MAX_LENGTH
        # Службы уведомлений принимают только стандартный порт https.
        or port not in (None, 443)
        or parts.scheme != "https"
        or not parts.hostname
        or not parts.hostname.isascii()
        or parts.username is not None
        or parts.password is not None
        or any(char.isspace() for char in address)
    ):
        raise not_a_service
    host = parts.hostname.lower()
    if not any(host == service or host.endswith(f".{service}") for service in PUSH_SERVICES):
        raise RuleViolationError(
            "Подписка не от службы уведомлений браузера: принимаются Apple, Google, "
            "Mozilla и Microsoft",
            detail=host,
        )

    public = decode_key(p256dh.strip())
    secret = decode_key(auth.strip())
    if len(public) != P256DH_BYTES or public[0] != 0x04 or len(secret) != AUTH_BYTES:
        raise RuleViolationError("Ключ подписки повреждён: включите уведомления заново")
    return Subscription(endpoint=address, p256dh=p256dh.strip(), auth=auth.strip())


def device_name(user_agent: str | None) -> str:
    """Как назвать устройство в «Включены на iPhone руководителя».

    По заголовку браузера, а не по выбору человека: спрашивать название — лишний шаг в
    момент, когда руководитель включает уведомления. iPad с iPadOS 13 и новее называет себя
    «Macintosh» и будет подписан как Mac: различить их можно только по сенсорному экрану, а
    его видит браузер, не сервер.
    """
    agent = user_agent or ""
    for marker, name in _DEVICES:
        if marker in agent:
            return name
    return UNKNOWN_DEVICE


def summary_key(day: date, user_id: uuid.UUID) -> str:
    """Ключ повтора сводки: одна за сутки одному человеку (инвариант 10)."""
    return f"morning-summary:{day.isoformat()}:{user_id}"


def question_key(question_id: uuid.UUID) -> str:
    """Ключ повтора вопроса: один пуш на вопрос (V27)."""
    return f"question:{question_id}"


def summary_payload(day: date, lock_screen: dict[str, Any]) -> dict[str, Any]:
    """Содержимое пуша сводки: то же, что вкладка «Сводка» показывает предпросмотром.

    `tag` — метка уведомления на устройстве: повторная доставка той же сводки заменяет
    прежнюю, а не добавляет вторую. Это запасной замок идемпотентности на случай, когда
    отправка ушла, а запись о ней — нет (`app.services.summary.send`).
    """
    return {
        "kind": "summary",
        "tag": f"morning-summary:{day.isoformat()}",
        "url": SUMMARY_URL,
        "lock_screen": lock_screen,
    }


def preview(text: str, limit: int) -> str:
    """Текст, укороченный до `limit` символов с «…» в конце, — для пуша.

    Одно правило на все поля пуша: предел содержимого держит домен, а не отправка. Иначе
    длинное название обнаруживалось бы отказом отправителя — каждое утро, как сбой службы
    уведомлений, пока строка стоит первой.
    """
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def question_payload(question_id: uuid.UUID, *, title: str | None, text: str) -> dict[str, Any]:
    """Содержимое пуша «ждёт вашего решения»: к чему вопрос и сам вопрос."""
    return {
        "kind": "question",
        "tag": f"question:{question_id}",
        "url": SUMMARY_URL,
        "title": None if title is None else preview(title, PUSH_FIELD_LENGTH),
        "question": preview(text, QUESTION_PREVIEW_LENGTH),
    }


def summary_due(local_now: time, send_at: str) -> bool:
    """Пора ли сводке: местное время дошло до назначенного (V24).

    Сравнение «не раньше», а не «ровно»: расписание зовёт раз в десять минут, и в назначенную
    минуту вызова может не быть вовсе — GitHub запаздывает в начале часа.
    """
    return local_now >= time.fromisoformat(send_at)


def summary_blocker(
    *, local_now: time, send_at: str, configured: bool, has_device: bool
) -> SummaryOutcome | None:
    """Что мешает отправить сводку сейчас; `None` — ничего, пора.

    «Некому» и «нечем» — не отправка, а ожидание: день остаётся свободным, и первый вызов
    расписания после того, как руководитель включил уведомления или заказчик ввёл ключ,
    сводку отправит — до последнего вызова утра (`LAST_SUMMARY_RUN`).
    """
    if not summary_due(local_now, send_at):
        return SummaryOutcome.NOT_YET
    if not configured:
        return SummaryOutcome.NOT_CONFIGURED
    if not has_device:
        return SummaryOutcome.NO_DEVICE
    return None
