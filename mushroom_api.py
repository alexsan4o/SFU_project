"""Клиент Kindwise Mushroom ID API с повторами и типизированными ошибками."""
import asyncio
import base64
import logging

import httpx

logger = logging.getLogger(__name__)


# --- Иерархия ошибок, чтобы бот мог по-разному реагировать ---
class MushroomAPIError(Exception):
    """Базовая ошибка работы с API распознавания."""


class AuthError(MushroomAPIError):
    """Неверный или отозванный API-ключ (401/403)."""


class QuotaError(MushroomAPIError):
    """Исчерпан лимит/кредиты тарифа (402)."""


class RateLimitError(MushroomAPIError):
    """Слишком много запросов (429)."""


class BadRequestError(MushroomAPIError):
    """Некорректный запрос (прочие 4xx), например битое изображение."""


class ServiceError(MushroomAPIError):
    """Временная ошибка сервиса (5xx)."""


class NetworkError(MushroomAPIError):
    """Сетевая ошибка или таймаут."""


# Коды, при которых имеет смысл повторить запрос
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _detect_mime(image_bytes: bytes) -> str:
    """Определяет MIME-тип изображения по сигнатуре (magic bytes).

    Нужно, чтобы не помечать PNG/WebP/GIF как JPEG в data-URI запроса.
    """
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "image/jpeg"  # запасной вариант для неизвестных форматов


def _map_status_error(status: int, body: str) -> MushroomAPIError:
    if status in (401, 403):
        return AuthError(f"API отклонил ключ (HTTP {status}).")
    if status == 402:
        return QuotaError(f"Исчерпан лимит запросов тарифа (HTTP {status}).")
    if status == 429:
        return RateLimitError(f"Превышена частота запросов (HTTP {status}).")
    if 400 <= status < 500:
        return BadRequestError(f"Некорректный запрос (HTTP {status}): {body[:200]}")
    return ServiceError(f"Сбой сервиса распознавания (HTTP {status}).")


async def identify(
    image_bytes: bytes,
    *,
    api_key: str,
    api_url: str,
    language: str = "ru",
    timeout: float = 30.0,
    max_retries: int = 3,
    backoff: float = 1.5,
    client: httpx.AsyncClient | None = None,
) -> dict:
    """Отправляет изображение в API и возвращает разобранный JSON-ответ.

    При временных сбоях (таймаут, сеть, 429/5xx) повторяет запрос с
    экспоненциальной задержкой. При постоянных ошибках бросает
    соответствующий подкласс MushroomAPIError.
    """
    if not image_bytes:
        raise BadRequestError("Пустое изображение.")

    # Хотя бы одна попытка, даже если в конфиге указали 0 или отрицательное число
    attempts = max(1, max_retries)

    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    mime = _detect_mime(image_bytes)
    payload = {
        "images": [f"data:{mime};base64,{image_b64}"],
        "similar_images": True,
    }
    headers = {"Api-Key": api_key, "Content-Type": "application/json"}
    params = {
        "details": "common_names,edibility,toxicity,description",
        "language": language,
    }

    # Позволяем переиспользовать клиент (удобно для тестов и пула соединений)
    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=timeout)

    try:
        last_exc: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                resp = await client.post(api_url, json=payload, headers=headers, params=params)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_exc = NetworkError(f"Сетевая ошибка: {exc}")
                logger.warning("Сетевая ошибка (попытка %d/%d): %s", attempt, attempts, exc)
            else:
                if resp.status_code in (200, 201):
                    try:
                        return resp.json()
                    except ValueError as exc:
                        raise ServiceError(f"Сервис вернул не-JSON ответ: {exc}") from exc

                err = _map_status_error(resp.status_code, resp.text)
                # Постоянные ошибки не повторяем
                if resp.status_code not in _RETRYABLE_STATUS:
                    raise err
                last_exc = err
                logger.warning(
                    "Временная ошибка API (попытка %d/%d): HTTP %d",
                    attempt, attempts, resp.status_code,
                )

            # Перед следующей попыткой ждём с нарастающей задержкой
            if attempt < attempts:
                await asyncio.sleep(backoff * (2 ** (attempt - 1)))

        # Повторы исчерпаны
        assert last_exc is not None
        raise last_exc
    finally:
        if own_client:
            await client.aclose()
