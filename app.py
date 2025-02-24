import os
import logging
import asyncio
import requests
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ------------------------------
# Конфигурация
# ------------------------------
API_KEY = os.getenv("PP_API_KEY", "ВАШ_API_КЛЮЧ")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "ВАШ_CHAT_ID")
BASE_API_URL = "https://api.alanbase.com/v1"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://apiposts-production-1dea.up.railway.app/webhook")
PORT = int(os.environ.get("PORT", 8080))

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------
# Инициализация Telegram-бота
# ------------------------------
application = Application.builder().token(TELEGRAM_TOKEN).build()

async def init_application():
    logger.info("Запуск инициализации Telegram бота...")
    await application.initialize()
    logger.info("Бот инициализирован!")

    await application.start()
    logger.info("Бот запущен!")

    logger.info("Инициализация Telegram бота завершена.")

# ------------------------------
# FastAPI сервер
# ------------------------------
app = FastAPI()

@app.post("/webhook")
async def telegram_webhook(request: Request):
    logger.info("Запрос получен в /webhook!")
    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"Ошибка парсинга JSON: {e}")
        return {"error": "Некорректный JSON"}, 400
    
    logger.info(f"Полученные данные: {data}")
    update = Update.de_json(data, application.bot)
    
    if not application.running:
        logger.warning("Telegram Application не запущено перед Webhook. Принудительная инициализация...")
        await init_application()

    try:
        await application.process_update(update)
        logger.info("Webhook успешно обработан.")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Ошибка обработки Webhook: {e}")
        return {"error": "Ошибка сервера"}, 500

# ------------------------------
# Telegram Bot Handlers & Buttons
# ------------------------------
async def send_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("📊 Статистика за день", callback_data='stats')],
                [InlineKeyboardButton("🚀 Тестовая конверсия", callback_data='test_conversion')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите команду:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    if query.data == "stats":
        date_today = datetime.now().strftime("%Y-%m-%d 00:00")
        params = {
            "group_by": "day",
            "timezone": "Europe/Moscow",
            "date_from": date_today,
            "date_to": date_today,
            "currency_code": "USD"
        }
        logger.info(f"Отправка запроса на статистику: {params}")
        response = requests.get(f"{BASE_API_URL}/partner/statistic/common", headers=headers, params=params)
        logger.info(f"Ответ API: {response.status_code} - {response.text}")
        
        if response.status_code == 200:
            await query.edit_message_text(f"📊 Статистика за день: {response.json()}")
        else:
            await query.edit_message_text(f"⚠️ Ошибка API {response.status_code}: {response.text}")
    elif query.data == "test_conversion":
        await query.edit_message_text("🚀 Отправка тестовой конверсии...")

application.add_handler(CommandHandler("start", send_buttons))
application.add_handler(CallbackQueryHandler(button_handler))
