import os
import logging
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ------------------------------
# Конфигурация
# ------------------------------
API_KEY = os.getenv("PP_API_KEY", "ВАШ_API_КЛЮЧ")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "ВАШ_CHAT_ID")
BASE_API_URL = "https://api.alanbase.com/api/v1"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://example.com")  # Укажи свой URL для webhook
PORT = int(os.getenv("PORT", 5000))

API_HEADERS = {
    "API-KEY": API_KEY,
    "Content-Type": "application/json",
    "User-Agent": "AlanbaseTelegramBot/1.0"
}

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------
# Flask API
# ------------------------------
app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
async def telegram_webhook():
    update = Update.de_json(request.get_json(), application.bot)
    await application.process_update(update)
    return "OK", 200

@app.route("/postback", methods=["POST"])
def postback():
    data = request.get_json()
    if not data or data.get("api_key") != API_KEY:
        return jsonify({"error": "Неверный API-ключ"}), 403

    message_text = (f"Новая конверсия!\n📌 Оффер: {data.get('offer_id', 'N/A')}\n")
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message_text}
    requests.post(telegram_url, json=payload)
    return jsonify({"status": "success"}), 200

# ------------------------------
# Telegram Бот
# ------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Статистика", callback_data='stats')],
                [InlineKeyboardButton("Конверсии", callback_data='conversions')],
                [InlineKeyboardButton("Офферы", callback_data='offers')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите команду:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    command = query.data
    text = ""
    if command == 'stats':
        text = "Запрос статистики отправлен."
    elif command == 'conversions':
        text = await get_conversions()
    elif command == 'offers':
        text = await get_offers()
    await query.edit_message_text(text=text)

async def get_conversions():
    url = f"{BASE_API_URL}/partner/statistic/conversions"
    response = requests.get(url, headers=API_HEADERS)
    if response.status_code == 200:
        data = response.json()
        return f"🔄 *Конверсии:* {data.get('meta', {}).get('total_count', 'N/A')}"
    return "Ошибка получения данных."

async def get_offers():
    url = f"{BASE_API_URL}/partner/offers"
    response = requests.get(url, headers=API_HEADERS)
    if response.status_code == 200:
        data = response.json()
        return f"📋 *Офферы:* {data.get('meta', {}).get('total_count', 'N/A')}"
    return "Ошибка API."

# ------------------------------
# Запуск бота
# ------------------------------
application = Application.builder().token(TELEGRAM_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(button_handler))

async def set_webhook():
    webhook_url = f"{WEBHOOK_URL}/webhook"
    await application.bot.set_webhook(webhook_url)
    logger.info(f"Webhook установлен: {webhook_url}")

if __name__ == "__main__":
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(set_webhook())
    app.run(host="0.0.0.0", port=PORT)
