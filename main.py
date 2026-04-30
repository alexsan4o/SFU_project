import os
import logging
import base64
import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Загружаем переменные из файла .env (если он есть)
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Ключи из переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MUSHROOM_API_KEY = os.getenv("MUSHROOM_API_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("Не задан TELEGRAM_TOKEN. Добавь его в файл .env или переменные окружения.")
if not MUSHROOM_API_KEY:
    raise RuntimeError("Не задан MUSHROOM_API_KEY. Добавь его в файл .env или переменные окружения.")

# URL API для распознавания грибов (пример: Kindwise Mushroom ID API)
MUSHROOM_API_URL = "https://mushroom.kindwise.com/api/v1/identification"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🍄 *Привет! Я бот для распознавания грибов.*\n\n"
        "Отправь мне фото гриба, и я скажу, что это за вид, "
        "съедобный ли он и какие у него особенности.\n\n"
        "⚠️ *Внимание:* результаты носят информационный характер. "
        "Никогда не употребляй в пищу грибы, определённые только по фото!",
        parse_mode="Markdown"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Как пользоваться ботом:*\n\n"
        "1. Сделай чёткое фото гриба\n"
        "2. Отправь его в этот чат\n"
        "3. Получи результат анализа\n\n"
        "💡 *Советы для лучшего распознавания:*\n"
        "• Снимай с близкого расстояния\n"
        "• Включи в кадр шляпку, ножку и пластинки\n"
        "• Используй хорошее освещение\n"
        "• Избегай размытых снимков",
        parse_mode="Markdown"
    )


async def analyze_mushroom(image_data: bytes) -> dict:
    """Отправляет фото в API и возвращает результат распознавания."""
    image_base64 = base64.b64encode(image_data).decode("utf-8")

    payload = {
        "images": [f"data:image/jpeg;base64,{image_base64}"],
        "similar_images": True,
    }

    headers = {
        "Api-Key": MUSHROOM_API_KEY,
        "Content-Type": "application/json",
    }

    # details и language передаются как query-параметры, не в теле запроса
    params = {
        "details": "common_names,edibility,toxicity,description",
        "language": "ru",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(MUSHROOM_API_URL, json=payload, headers=headers, params=params)
        response.raise_for_status()
        return response.json()


def format_result(data: dict) -> str:
    """Форматирует ответ API в читаемый текст."""
    try:
        result = data.get("result", {})
        classification = result.get("classification", {})
        suggestions = classification.get("suggestions", [])

        if not suggestions:
            return "😕 Не удалось распознать гриб. Попробуй сделать более чёткое фото."

        top = suggestions[0]
        name = top.get("name", "Неизвестно")
        probability = round(top.get("probability", 0) * 100, 1)

        # Дополнительные данные (если есть в ответе)
        details = top.get("details") or {}
        common_names = details.get("common_names") or []
        edibility = details.get("edibility") or ""
        desc_obj = details.get("description")
        description = (desc_obj.get("value") if isinstance(desc_obj, dict) else "") or ""
        toxicity = details.get("toxicity") or ""

        # Иконка съедобности (защита от None)
        edibility_lower = edibility.lower()
        edibility_icon = "✅" if "edible" in edibility_lower else ("☠️" if "poison" in edibility_lower or "toxic" in edibility_lower else "❓")

        lines = [
            f"🍄 *Результат распознавания*\n",
            f"*Вид:* {name}",
        ]

        if common_names:
            lines.append(f"*Народные названия:* {', '.join(common_names[:3])}")

        lines.append(f"*Уверенность:* {probability}%")

        if edibility:
            lines.append(f"*Съедобность:* {edibility_icon} {edibility}")

        if toxicity:
            lines.append(f"*Токсичность:* {toxicity}")

        if description:
            short_desc = description[:300] + "..." if len(description) > 300 else description
            lines.append(f"\n📝 *Описание:*\n{short_desc}")

        # Альтернативные варианты
        if len(suggestions) > 1:
            lines.append("\n🔍 *Другие возможные варианты:*")
            for s in suggestions[1:4]:
                alt_name = s.get("name", "?")
                alt_prob = round(s.get("probability", 0) * 100, 1)
                lines.append(f"  • {alt_name} — {alt_prob}%")

        lines.append(
            "\n\n⚠️ _Внимание: не собирай и не ешь грибы, опираясь только на результаты бота!_"
        )

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Ошибка форматирования результата: {e}")
        return "⚠️ Ошибка обработки ответа от сервиса. Попробуй позже."


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает входящие фото."""
    await update.message.reply_text("🔍 Анализирую фото, подожди немного...")

    try:
        # Берём фото наилучшего качества
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)

        # Скачиваем изображение
        image_data = await file.download_as_bytearray()

        # Отправляем в API
        result = await analyze_mushroom(bytes(image_data))

        # Форматируем и отправляем ответ
        text = format_result(result)
        await update.message.reply_text(text, parse_mode="Markdown")

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP ошибка API: {e.response.status_code} — {e.response.text}")
        await update.message.reply_text(
            f"❌ Ошибка сервиса распознавания (код {e.response.status_code}). "
            "Проверь API-ключ или попробуй позже."
        )
    except httpx.RequestError as e:
        logger.error(f"Сетевая ошибка: {e}")
        await update.message.reply_text("❌ Не удалось подключиться к сервису. Проверь интернет-соединение.")
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
        await update.message.reply_text("❌ Произошла ошибка. Попробуй позже.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 Пожалуйста, отправь *фото* гриба для анализа.\n"
        "Введи /help для справки.",
        parse_mode="Markdown"
    )


def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Бот запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()