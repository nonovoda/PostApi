import os
import logging
import asyncio
import httpx
from datetime import datetime
from fastapi import FastAPI, Request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ------------------------------
# Конфигурация
# ------------------------------
API_KEY = os.getenv("PP_API_KEY", "ВАШ_API_КЛЮЧ")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "ВАШ_CHAT_ID")
BASE_API_URL = "https://api.alanbase.com/v1"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-bot.onrender.com/webhook")
PORT = int(os.environ.get("PORT", 8000))

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------
# Инициализация Telegram-бота
# ------------------------------
application = Application.builder().token(TELEGRAM_TOKEN).build()

async def init_application():
    logger.info("Запуск Telegram бота...")
    await application.initialize()
    await application.start()
    logger.info("Бот запущен!")

# ------------------------------
# FastAPI сервер
# ------------------------------
app = FastAPI()

@app.post("/webhook")
async def telegram_webhook(request: Request):
    logger.info("Запрос получен в /webhook")
    try:
        data = await request.json()
        logger.info(f"Полученные данные: {data}")
    except Exception as e:
        logger.error(f"Ошибка JSON: {e}")
        return {"error": "Некорректный JSON"}, 400

    update = Update.de_json(data, application.bot)

    if not application.running:
        logger.warning("Telegram Application не запущено. Инициализируем...")
        await init_application()

    try:
        await application.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Ошибка обработки Webhook: {e}")
        return {"error": "Ошибка сервера"}, 500

# ------------------------------
# Telegram Bot Handlers & Reply-кнопки
# ------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["📊 Статистика за день", "🚀 Тестовая конверсия"],
                ["🔍 Детальная статистика", "📈 Топ офферы"],
                ["🔄 Обновить данные"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text("Выберите команду:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        text = update.message.text
    elif update.callback_query:
        text = update.callback_query.data
        await update.callback_query.answer()
    else:
        return

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    if text == "📊 Статистика за день":
        date_from = datetime.now().strftime("%Y-%m-%d 00:00")
        date_to = datetime.now().strftime("%Y-%m-%d 23:59")

        params = {
            "group_by": "day",
            "timezone": "Europe/Moscow",
            "date_from": date_from,
            "date_to": date_to,
            "currency_code": "USD"
        }
        logger.info(f"Отправка запроса на статистику без прокси: {params}")

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_API_URL}/partner/statistic/common", headers=headers, params=params)

        logger.info(f"Ответ API: {response.status_code} - {response.text}")

        message = f"📊 Статистика за день: {response.json()}" if response.status_code == 200 else f"⚠️ Ошибка API {response.status_code}: {response.text}"
        await update.message.reply_text(message)

    elif text == "🚀 Тестовая конверсия":
        await update.message.reply_text("🚀 Отправка тестовой конверсии...")
    elif text == "🔍 Детальная статистика":
        await update.message.reply_text("🔍 Запрос детальной статистики...")
    elif text == "📈 Топ офферы":
        await update.message.reply_text("📈 Запрос списка топ офферов...")
    elif text == "🔄 Обновить данные":
        await update.message.reply_text("🔄 Данные обновлены!")

application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))
