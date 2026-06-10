"""ГрибБот — Telegram-бот распознавания грибов. Релизная версия.

Запуск:  python bot.py
Переменные окружения берутся из .env или окружения сервера (см. .env.example).
"""
import logging
import logging.handlers
import sys

import httpx
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import mushroom_api as api
from config import ConfigError, Settings
from formatting import format_identification
from rate_limiter import RateLimiter

logger = logging.getLogger("gribbot")


# --------------------------------------------------------------------------
# Логирование
# --------------------------------------------------------------------------
def setup_logging(settings: Settings) -> None:
    level = getattr(logging, settings.log_level, logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if settings.log_file:
        handlers.append(
            logging.handlers.RotatingFileHandler(
                settings.log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
        )
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        handlers=handlers,
    )
    # Приглушаем болтливый httpx
    logging.getLogger("httpx").setLevel(logging.WARNING)


# --------------------------------------------------------------------------
# Тексты
# --------------------------------------------------------------------------
START_TEXT = (
    "🍄 <b>Привет! Я ГрибБот — помогаю распознавать грибы по фото.</b>\n\n"
    "Пришлите фотографию гриба, и я подскажу вид, съедобность и особенности.\n\n"
    "⚠️ <i>Результаты носят информационный характер. Никогда не употребляйте "
    "в пищу грибы, определённые только по фото!</i>"
)

HELP_TEXT = (
    "📖 <b>Как пользоваться ботом</b>\n\n"
    "1. Сделайте чёткое фото гриба\n"
    "2. Отправьте его в этот чат\n"
    "3. Получите результат анализа\n\n"
    "💡 <b>Советы для лучшего распознавания:</b>\n"
    "• Снимайте с близкого расстояния\n"
    "• Включите в кадр шляпку, ножку и пластинки\n"
    "• Используйте хорошее освещение\n"
    "• Избегайте размытых снимков\n\n"
    "Команды: /start, /help, /status"
)

ASK_PHOTO_TEXT = (
    "📸 Пожалуйста, отправьте <b>фото</b> гриба для анализа.\n"
    "Введите /help для справки."
)


# --------------------------------------------------------------------------
# Хендлеры команд
# --------------------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(START_TEXT, parse_mode=ParseMode.HTML)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("✅ Бот работает и готов принимать фото.")


# --------------------------------------------------------------------------
# Обработка фото
# --------------------------------------------------------------------------
async def _extract_image(update: Update, context: ContextTypes.DEFAULT_TYPE, settings: Settings):
    """Возвращает байты изображения из сообщения (фото или картинка-документ).

    Бросает ValueError с пользовательским текстом при проблеме.
    """
    message = update.message
    file_id = None
    file_size = None

    if message.photo:
        photo = message.photo[-1]  # наибольшее разрешение
        file_id = photo.file_id
        file_size = photo.file_size
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        file_id = message.document.file_id
        file_size = message.document.file_size
    else:
        raise ValueError(ASK_PHOTO_TEXT)

    if file_size and file_size > settings.max_image_bytes:
        raise ValueError(
            f"📁 Файл слишком большой ({file_size // (1024*1024)} МБ). "
            f"Максимум — {settings.max_image_bytes // (1024*1024)} МБ."
        )

    tg_file = await context.bot.get_file(file_id)
    data = await tg_file.download_as_bytearray()
    if len(data) > settings.max_image_bytes:
        raise ValueError("📁 Изображение слишком большое для обработки.")
    return bytes(data)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None or message.from_user is None:
        return

    settings: Settings = context.application.bot_data["settings"]
    limiter: RateLimiter = context.application.bot_data["limiter"]
    user_id = message.from_user.id

    # Анти-спам
    if not limiter.allow(user_id):
        wait = int(limiter.retry_after(user_id)) + 1
        await message.reply_text(f"⏳ Слишком много запросов. Подождите ~{wait} сек и попробуйте снова.")
        return

    placeholder = await message.reply_text("🔍 Анализирую фото, подождите немного…")

    try:
        image = await _extract_image(update, context, settings)
    except ValueError as exc:
        await placeholder.edit_text(str(exc), parse_mode=ParseMode.HTML)
        return
    except Exception as exc:  # ошибка скачивания файла из Telegram
        logger.exception("Не удалось получить изображение: %s", exc)
        await placeholder.edit_text("❌ Не удалось загрузить изображение. Попробуйте ещё раз.")
        return

    # Показываем индикатор «печатает…», пока ждём ответ API
    try:
        await context.bot.send_chat_action(message.chat_id, ChatAction.TYPING)
    except Exception:
        pass

    client: httpx.AsyncClient = context.application.bot_data["http_client"]
    try:
        data = await api.identify(
            image,
            api_key=settings.mushroom_api_key,
            api_url=settings.api_url,
            language=settings.language,
            timeout=settings.request_timeout,
            max_retries=settings.max_retries,
            backoff=settings.retry_backoff,
            client=client,
        )
    except api.AuthError:
        logger.error("API отклонил ключ — проверьте MUSHROOM_API_KEY.")
        await placeholder.edit_text("❌ Сервис распознавания недоступен (ошибка ключа). Сообщите администратору.")
        return
    except api.QuotaError:
        logger.warning("Исчерпан лимит API.")
        await placeholder.edit_text("❌ На сегодня лимит запросов исчерпан. Попробуйте позже.")
        return
    except api.RateLimitError:
        await placeholder.edit_text("⏳ Сервис распознавания перегружен. Попробуйте через минуту.")
        return
    except api.BadRequestError:
        await placeholder.edit_text("🖼 Не удалось обработать это изображение. Пришлите другое фото гриба.")
        return
    except (api.ServiceError, api.NetworkError) as exc:
        logger.warning("Временная недоступность API: %s", exc)
        await placeholder.edit_text("❌ Сервис временно недоступен. Попробуйте через несколько минут.")
        return
    except Exception as exc:
        logger.exception("Неожиданная ошибка при обращении к API: %s", exc)
        await placeholder.edit_text("❌ Произошла внутренняя ошибка. Попробуйте позже.")
        return

    text = format_identification(data, settings.confidence_threshold)
    try:
        await placeholder.edit_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    except Exception as exc:
        # На случай, если HTML всё же не прошёл — отправляем без разметки
        logger.warning("Не удалось отправить HTML-ответ (%s), отправляю plain text.", exc)
        import re
        plain = re.sub(r"<[^>]+>", "", text)
        await placeholder.edit_text(plain, disable_web_page_preview=True)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(ASK_PHOTO_TEXT, parse_mode=ParseMode.HTML)


# --------------------------------------------------------------------------
# Глобальный обработчик ошибок — бот не должен падать
# --------------------------------------------------------------------------
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Необработанная ошибка в обработчике: %s", context.error)
    try:
        if isinstance(update, Update) and update.effective_message:
            await update.effective_message.reply_text("❌ Что-то пошло не так. Попробуйте ещё раз позже.")
    except Exception:
        pass


# --------------------------------------------------------------------------
# Сборка приложения и запуск
# --------------------------------------------------------------------------
async def _post_init(app: Application) -> None:
    app.bot_data["http_client"] = httpx.AsyncClient(
        timeout=app.bot_data["settings"].request_timeout
    )
    logger.info("HTTP-клиент инициализирован.")


async def _post_shutdown(app: Application) -> None:
    client = app.bot_data.get("http_client")
    if client is not None:
        await client.aclose()
        logger.info("HTTP-клиент закрыт.")


def build_application(settings: Settings) -> Application:
    app = (
        ApplicationBuilder()
        .token(settings.telegram_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )
    app.bot_data["settings"] = settings
    app.bot_data["limiter"] = RateLimiter(settings.rate_limit_count, settings.rate_limit_window)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(on_error)
    return app


def main() -> int:
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        # До настройки логирования — печатаем прямо в stderr
        print(f"[КОНФИГ] {exc}", file=sys.stderr)
        return 2

    setup_logging(settings)
    logger.info("Запуск ГрибБота…")
    app = build_application(settings)
    # drop_pending_updates=True: при рестарте не разгребаем накопившуюся очередь
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
