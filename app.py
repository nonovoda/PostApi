import os
import logging
import requests
from threading import Thread
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext

# ------------------------------
# 🔹 Конфигурация
# ------------------------------
API_KEY = os.getenv("PP_API_KEY", "ВАШ_API_КЛЮЧ")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "ВАШ_CHAT_ID")

# Базовый URL для Alanbase Partner API
BASE_API_URL = "https://api.alanbase.com/api/v1"

# Заголовки для запросов к API
API_HEADERS = {
    "API-KEY": API_KEY,
    "Content-Type": "application/json"
}

# Логирование работы бота
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------
# 🔹 Flask API (Постбеки + Статистика + Баланс)
# ------------------------------
app = Flask(__name__)

@app.route('/postback', methods=['GET', 'POST'])
def postback():
    """ Принимает данные от партнёрской программы и отправляет в Telegram. """
    data = request.get_json() or request.args

    if not data:
        return jsonify({"error": "Нет данных в запросе"}), 400

    if not data.get('api_key'):
        return jsonify({"error": "Не передан API-ключ"}), 400
    if data.get('api_key') != API_KEY:
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
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message_text, "parse_mode": "Markdown"}
    requests.post(telegram_url, json=payload)

    return jsonify({"status": "success"}), 200

@app.route('/test', methods=['GET'])
def test():
    """ Отправляет тестовое сообщение в Telegram. """
    test_message = "Тестовое сообщение!\nПроверка работы бота."
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": test_message, "parse_mode": "Markdown"}
    requests.post(telegram_url, json=payload)

    return jsonify({"status": "Тестовое сообщение успешно отправлено"}), 200

@app.route('/stats', methods=['GET'])
def stats():
    """ Получает общую статистику из API и отправляет в Telegram. """
    url = f"{BASE_API_URL}/partner/statistic/common"
    response = requests.get(url, headers=API_HEADERS)

    if response.status_code == 200:
        data = response.json()
        meta = data.get("meta", {})
        stats_message = (
            "📊 *Общая статистика:*\n"
            f"Страница: {meta.get('page', 'N/A')}\n"
            f"Записей: {meta.get('per_page', 'N/A')}\n"
            f"Всего: {meta.get('total_count', 'N/A')}\n"
            f"Последняя страница: {meta.get('last_page', 'N/A')}\n"
        )

        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": stats_message, "parse_mode": "Markdown"}
        requests.post(telegram_url, json=payload)

        return jsonify({"status": "Статистика отправлена в Telegram"}), 200
    else:
        return jsonify({"error": "Ошибка получения данных из API", "details": response.text}), 500

@app.route('/balance', methods=['GET'])
def balance():
    """ Получает баланс (только USD) из API и отправляет в Telegram. """
    url = f"{BASE_API_URL}/partner/balance"
    response = requests.get(url, headers=API_HEADERS)

    if response.status_code == 200:
        data = response.json()
        balances = data.get("data", [])

        balance_usd = "Нет данных"
        for entry in balances:
            if entry.get("currency_code") == "USD":
                balance_usd = entry.get("balance", 0)

        balance_text = f"💰 *Ваш баланс (USD):* {balance_usd}"

        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": balance_text, "parse_mode": "Markdown"}
        requests.post(telegram_url, json=payload)

        return jsonify({"status": "Баланс отправлен в Telegram"}), 200
    else:
        return jsonify({"error": "Ошибка получения данных из API", "details": response.text}), 500

# ------------------------------
# 🔹 Telegram-бот (кнопки + команды)
# ------------------------------
def start(update: Update, context: CallbackContext) -> None:
    """ Отправляет inline-кнопки при старте бота. """
    keyboard = [
        [InlineKeyboardButton("Статистика", callback_data='stats')],
        [InlineKeyboardButton("Баланс (USD)", callback_data='balance')],
        [InlineKeyboardButton("Тест", callback_data='test')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Выберите команду:", reply_markup=reply_markup)

def button_handler(update: Update, context: CallbackContext) -> None:
    """ Обрабатывает нажатия на inline-кнопки. """
    query = update.callback_query
    query.answer()
    command = query.data
    text = ""

    if command == 'balance':
        text = balance().json["status"]
    elif command == 'stats':
        text = stats().json["status"]
    elif command == 'test':
        text = test().json["status"]
    else:
        text = "Неизвестная команда."

    query.edit_message_text(text=text, parse_mode='Markdown')

# ------------------------------
# 🔹 Запуск Flask и Telegram-бота
# ------------------------------
def run_flask():
    """ Запускает Flask API. """
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

def run_telegram_bot():
    """ Запускает Telegram-бота. """
    updater = Updater(TELEGRAM_TOKEN)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.a
