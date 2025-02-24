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
WEBHOOK_URL = "https://apiposts-production-1dea.up.railway.app/webhook"
PORT = int(os.getenv("PORT", 5000))

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------
# Инициализация Telegram-бота
# ------------------------------
application = Application.builder().token(TELEGRAM_TOKEN).build()

async def init_application():
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

# ------------------------------
# FastAPI сервер
# ------------------------------
app = FastAPI()

@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"status": "ok"}

@app.post("/postback")
async def postback(request: Request):
    data = await request.json()
    logger.info("Полученные данные в /postback: %s", data)
    
    if not data or data.get("api_key") != API_KEY:
        return {"error": "Неверный API-ключ"}

    message_text = (
        "Новая конверсия!\n"
        f"📌 Оффер: {data.get('offer_id', 'N/A')}\n"
        f"🛠 Подход: {data.get('sub_id_2', 'N/A')}\n"
        f"📊 Тип конверсии: {data.get('goal', 'N/A')}\n"
        f"⚙️ Статус конверсии: {data.get('status', 'N/A')}\n"
        f"🎯 Кампания: {data.get('sub_id_4', 'N/A')}\n"
        f"🎯 Адсет: {data.get('sub_id_5', 'N/A')}\n"
        f"⏰ Время конверсии: {data.get('conversion_date', 'N/A')}\n"
    )
    await application.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message_text)
    return {"status": "success"}

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
    await init_application()
    await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")

if __name__ == "__main__":
    import uvicorn

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
