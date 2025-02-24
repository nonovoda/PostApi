import os
import logging
import asyncio
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
PORT = int(os.getenv("PORT", 5000))

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

    await application.updater.start_polling()
    logger.info("Polling запущен!")
    logger.info("Инициализация Telegram бота завершена.")

# ------------------------------
# FastAPI сервер
# ------------------------------
app = FastAPI()

@app.post("/webhook")
async def telegram_webhook(request: Request):
    logger.info("Запрос получен в /webhook!")

    # Гарантируем, что бот запущен перед обработкой Webhook
    if not application.running:
        logger.warning("Telegram Application не запущено перед Webhook. Принудительная инициализация...")
        await init_application()  # Запускаем бота принудительно!

    data = await request.json()
    logger.info(f"Полученные данные: {data}")

    update = Update.de_json(data, application.bot)

    try:
        await application.process_update(update)
        logger.info("Webhook успешно обработан.")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Ошибка обработки Webhook: {e}")
        return {"error": "Ошибка сервера"}, 500

# ------------------------------
# Telegram Bot Handlers
# ------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [{"text": "Статистика", "callback_data": "stats"}],
        [{"text": "Конверсии", "callback_data": "conversions"}],
        [{"text": "Офферы", "callback_data": "offers"}],
        [{"text": "Тест", "callback_data": "test"}],
    ]
    reply_markup = {"inline_keyboard": keyboard}
    await update.message.reply_text("Выберите команду:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    command = query.data
    text = ""

    if command == "stats":
        text = "Запрос статистики отправлен."
    elif command == "conversions":
        text = "Запрос конверсий отправлен."
    elif command == "offers":
        text = "Запрос офферов отправлен."
    elif command == "test":
        text = "Тестовое сообщение отправлено."
    else:
        text = "Неизвестная команда."

    await query.edit_message_text(text=text)

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
    loop.run_until_complete(main())  # Запускаем бота перед сервером FastAPI!
    uvicorn.run(app, host="0.0.0.0", port=PORT)
