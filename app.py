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
    logger.info("Полученные данные в /postback: %s", data)
    if not data or data.get("api_key") != API_KEY:
        return jsonify({"error": "Неверный API-ключ"}), 403

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
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message_text}
    requests.post(telegram_url, json=payload)
    return jsonify({"status": "success"}), 200

async def get_conversions():
    params = {
        "timezone": "Europe/Moscow",
        "date_from": (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
        "date_to": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "statuses": [0, 1, 2, 4],
        "per_page": 1000
    }
    url = f"{BASE_API_URL}/partner/statistic/conversions"
    response = requests.get(url, headers=API_HEADERS, params=params)
    if response.status_code == 200:
        data = response.json()
        return f"🔄 *Конверсии:* {data.get('meta', {}).get('total_count', 'N/A')}"
    return "Ошибка получения данных."

async def get_offers():
    params = {
        "is_avaliable": 1,
        "per_page": 100
    }
    url = f"{BASE_API_URL}/partner/offers"
    response = requests.get(url, headers=API_HEADERS, params=params)
    if response.status_code == 200:
        data = response.json()
        return f"📋 *Офферы:* {data.get('meta', {}).get('total_count', 'N/A')}"
    return "Ошибка API."

async def get_common_stats():
    params = {
        "group_by": "day",
        "timezone": "Europe/Moscow",
        "date_from": (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d 00:00"),
        "date_to": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    url = f"{BASE_API_URL}/partner/statistic/common"
    response = requests.get(url, headers=API_HEADERS, params=params)
    if response.status_code == 200:
        data = response.json()
        return f"📊 Статистика за неделю:\n{data}"
    return "Ошибка получения статистики."

async def get_conversion_details(conversion_id):
    url = f"{BASE_API_URL}/partner/statistic/conversions/{conversion_id}"
    response = requests.get(url, headers=API_HEADERS)
    if response.status_code == 200:
        data = response.json()
        return f"📊 Детали конверсии {conversion_id}:\n{data}"
    return "Ошибка получения данных о конверсии."

async def set_webhook():
    webhook_url = f"{WEBHOOK_URL}/webhook"
    await application.bot.set_webhook(webhook_url)
    logger.info(f"Webhook установлен: {webhook_url}")

if __name__ == "__main__":
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(set_webhook())
    app.run(host="0.0.0.0", port=PORT)
