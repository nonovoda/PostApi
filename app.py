import os
import logging
import asyncio
import requests
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from telegram import Update
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

# ------------------------------
# API-запросы к ПП
# ------------------------------
async def get_common_stats():
    url = f"{BASE_API_URL}/partner/statistic/common"
    params = {
        "group_by": "day",
        "timezone": "Europe/Moscow",
        "date_from": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d 00:00"),
        "date_to": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    response = requests.get(url, headers={"API-KEY": API_KEY}, params=params)
    return response.json() if response.status_code == 200 else {"error": "Ошибка получения статистики"}

async def get_offers():
    url = f"{BASE_API_URL}/partner/offers"
    response = requests.get(url, headers={"API-KEY": API_KEY})
    return response.json() if response.status_code == 200 else {"error": "Ошибка получения офферов"}

async def get_conversions():
    url = f"{BASE_API_URL}/partner/statistic/conversions"
    params = {
        "timezone": "Europe/Moscow",
        "date_from": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
        "date_to": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "statuses": [0, 1, 2, 4],
        "per_page": 100
    }
    response = requests.get(url, headers={"API-KEY": API_KEY}, params=params)
    return response.json() if response.status_code == 200 else {"error": "Ошибка получения конверсий"}

# ------------------------------
# Telegram Bot Handlers
# ------------------------------
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = await get_common_stats()
    await update.message.reply_text(f"📊 Статистика: {stats}")

async def offers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    offers = await get_offers()
    await update.message.reply_text(f"📋 Офферы: {offers}")

async def conversions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conversions = await get_conversions()
    await update.message.reply_text(f"🔄 Конверсии: {conversions}")

application.add_handler(CommandHandler("stats", stats_command))
application.add_handler(CommandHandler("offers", offers_command))
application.add_handler(CommandHandler("conversions", conversions_command))

# ------------------------------
# Установка Webhook
# ------------------------------
async def main():
    logger.info("Вызов main()...")
    await init_application()
    logger.info(f"Установка Webhook: {WEBHOOK_URL}/webhook")
    await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    logger.info("Webhook установлен!")

if __name__ == "__main__":
    import uvicorn

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
