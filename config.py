"""Конфигурация бота. Все настройки берутся из переменных окружения / .env."""
import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # dotenv не обязателен в проде, если переменные заданы иначе
    pass


class ConfigError(RuntimeError):
    """Ошибка конфигурации (отсутствует обязательная переменная и т.п.)."""


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"Переменная {name} должна быть целым числом, получено: {raw!r}")


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        raise ConfigError(f"Переменная {name} должна быть числом, получено: {raw!r}")


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    mushroom_api_key: str
    api_url: str = "https://mushroom.kindwise.com/api/v1/identification"
    language: str = "ru"

    # Поведение / надёжность
    request_timeout: float = 30.0          # таймаут запроса к API, сек
    max_retries: int = 3                   # число повторов при временных сбоях
    retry_backoff: float = 1.5             # базовая задержка между повторами, сек
    max_image_bytes: int = 12 * 1024 * 1024  # макс. размер фото, байт (12 МБ)

    # Анти-спам: не более N запросов за window секунд на пользователя
    rate_limit_count: int = 5
    rate_limit_window: float = 60.0

    # Порог уверенности: ниже него вердикт считается ненадёжным
    confidence_threshold: float = 0.80

    # Логирование
    log_level: str = "INFO"
    log_file: str = field(default="")  # пусто = только консоль

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("TELEGRAM_TOKEN", "").strip()
        api_key = os.getenv("MUSHROOM_API_KEY", "").strip()

        missing = []
        if not token:
            missing.append("TELEGRAM_TOKEN")
        if not api_key:
            missing.append("MUSHROOM_API_KEY")
        if missing:
            raise ConfigError(
                "Не заданы обязательные переменные окружения: "
                + ", ".join(missing)
                + ". Заполните их в файле .env или окружении сервера."
            )

        return cls(
            telegram_token=token,
            mushroom_api_key=api_key,
            api_url=os.getenv("MUSHROOM_API_URL", cls.api_url).strip() or cls.api_url,
            language=os.getenv("API_LANGUAGE", cls.language).strip() or cls.language,
            request_timeout=_get_float("REQUEST_TIMEOUT", cls.request_timeout),
            max_retries=_get_int("MAX_RETRIES", cls.max_retries),
            retry_backoff=_get_float("RETRY_BACKOFF", cls.retry_backoff),
            max_image_bytes=_get_int("MAX_IMAGE_BYTES", cls.max_image_bytes),
            rate_limit_count=_get_int("RATE_LIMIT_COUNT", cls.rate_limit_count),
            rate_limit_window=_get_float("RATE_LIMIT_WINDOW", cls.rate_limit_window),
            confidence_threshold=_get_float("CONFIDENCE_THRESHOLD", cls.confidence_threshold),
            log_level=os.getenv("LOG_LEVEL", cls.log_level).strip().upper() or cls.log_level,
            log_file=os.getenv("LOG_FILE", "").strip(),
        )
