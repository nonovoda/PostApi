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
BASE_API_URL = "https://api.alanbase.com/api/v1"
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
    data = await request.json()
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

@app.post("/postback")
async def postback(request: Request):
    logger.info("Запрос получен в /postback!")
    data = await request.json()
    logger.info(f"Полученные данные: {data}")

    if not data or data.get("api_key") != API_KEY:
        logger.error("Ошибка: Неверный API-ключ")
        return {"error": "Неверный API-ключ"}, 403

    message_text = (
        "📌 Оффер: {offer_id}\n"
        "🛠 Подход: {sub_id_2}\n"
        "📊 Тип конверсии: {goal}\n"
        "⚙️ Статус: {status}\n"
        "🎯 Кампания: {sub_id_4}\n"
        "🎯 Адсет: {sub_id_5}\n"
        "⏰ Время: {conversion_date}"
    ).format(
        offer_id=data.get("offer_id", "N/A"),
        sub_id_2=data.get("sub_id_2", "N/A"),
        goal=data.get("goal", "N/A"),
        status=data.get("status", "N/A"),
        sub_id_4=data.get("sub_id_4", "N/A"),
        sub_id_5=data.get("sub_id_5", "N/A"),
        conversion_date=data.get("conversion_date", "N/A")
    )

    await application.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message_text)
    return {"status": "success"}

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
    if query.data == "stats":
        date = datetime.now().strftime("%Y-%m-%d 00:00")
        response = requests.get(f"{BASE_API_URL}/partner/statistic/common", 
                                headers={"API-KEY": API_KEY},
                                params={"date_from": date, "date_to": date, "group_by": "day", "timezone": "Europe/Moscow"})
        await query.edit_message_text(f"📊 Статистика за день: {response.json()}")
    elif query.data == "test_conversion":
        await query.edit_message_text("🚀 Отправка тестовой конверсии...")

application.add_handler(CommandHandler("start", send_buttons))
application.add_handler(CallbackQueryHandler(button_handler))
