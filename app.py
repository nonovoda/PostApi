import os
import logging
import requests
from threading import Thread
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext

# ------------------------------
# Конфигурация
# ------------------------------
API_KEY = os.getenv("PP_API_KEY", "ВАШ_API_КЛЮЧ")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "ВАШ_CHAT_ID")

# Базовый URL для Alanbase Partner API
BASE_API_URL = "https://api.alanbase.com/api/v1"

# Заголовки для запросов к API (с добавленным User-Agent)
API_HEADERS = {
    "API-KEY": API_KEY,
    "Content-Type": "application/json",
    "User-Agent": "AlanbaseTelegramBot/1.0"
}

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------
# Flask API (Постбеки + Тест + Статистика + Баланс + Офферы)
# ------------------------------
app = Flask(__name__)

@app.route('/postback', methods=['GET', 'POST'])
def postback():
    """Принимает данные от партнёрской программы и пересылает их в Telegram."""
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
    """Тестовый endpoint для отправки тестового сообщения в Telegram."""
    test_message = "Тестовое сообщение!\nПроверка работы бота."
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": test_message, "parse_mode": "Markdown"}
    requests.post(telegram_url, json=payload)
    return jsonify({"status": "Тестовое сообщение успешно отправлено"}), 200

@app.route('/stats', methods=['GET'])
def stats():
    """Получает общую статистику из API и отправляет её в Telegram."""
    url = f"{BASE_API_URL}/partner/statistic/common"
    response = requests.get(url, headers=API_HEADERS)
    if response.status_code == 200:
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            return jsonify({"error": "Неверный формат ответа от API", "raw_response": response.text}), 500

        meta = data.get("meta", {})
        stats_message = (
            "📊 *Общая статистика:*\n"
            f"Страница: {meta.get('page', 'N/A')}\n"
            f"Записей на странице: {meta.get('per_page', 'N/A')}\n"
            f"Всего записей: {meta.get('total_count', 'N/A')}\n"
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
    """Получает баланс (только USD) из API и отправляет в Telegram."""
    url = f"{BASE_API_URL}/partner/balance"
    response = requests.get(url, headers=API_HEADERS)
    if response.status_code == 200:
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            return jsonify({"error": "Неверный формат ответа от API", "raw_response": response.text}), 500

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

@app.route('/offers', methods=['GET'])
def offers():
    """Получает список офферов из API и отправляет краткую информацию в Telegram."""
    url = f"{BASE_API_URL}/partner/offers"
    response = requests.get(url, headers=API_HEADERS)
    if response.status_code == 200:
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            return jsonify({"error": "Неверный формат ответа от API", "raw_response": response.text}), 500

        offers_list = data.get("data", [])
        meta = data.get("meta", {})
        if not offers_list:
            offers_text = "⚠️ Офферы не найдены."
        else:
            offers_text = "📋 *Список офферов:*\n"
            offers_text += f"Всего офферов: {meta.get('total_count', 'N/A')}\n"
            # Можно вывести, например, первые 3 оффера
            for offer in offers_list[:3]:
                name = offer.get("name", "N/A")
                offer_id = offer.get("id", "N/A")
                offers_text += f"🔹 {name} (ID: {offer_id})\n"
            if meta.get("total_count", 0) > 3:
                offers_text += "… и другие"
        
        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": offers_text, "parse_mode": "Markdown"}
        requests.post(telegram_url, json=payload)
        return jsonify({"status": "Офферы отправлены в Telegram"}), 200
    else:
        return jsonify({"error": "Ошибка получения данных из API", "details": response.text}), 500

# ------------------------------
# Telegram-бот с inline-кнопками
# ------------------------------
def start(update: Update, context: CallbackContext) -> None:
    """Отправляет inline-кнопки при команде /start."""
    keyboard = [
        [InlineKeyboardButton("Статистика", callback_data='stats')],
        [InlineKeyboardButton("Баланс (USD)", callback_data='balance')],
        [InlineKeyboardButton("Офферы", callback_data='offers')],
        [InlineKeyboardButton("Тест", callback_data='test')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Выберите команду:", reply_markup=reply_markup)

def button_handler(update: Update, context: CallbackContext) -> None:
    """Обрабатывает нажатия на inline-кнопки и вызывает соответствующие API-запросы."""
    query = update.callback_query
    query.answer()
    command = query.data
    text = ""

    if command == 'balance':
        text = get_balance()
    elif command == 'stats':
        text = "Запрос статистики отправлен."  # Можно расширить вызовом функции stats()
    elif command == 'offers':
        text = get_offers()
    elif command == 'test':
        text = "Тестовое сообщение отправлено."
    else:
        text = "Неизвестная команда."

    query.edit_message_text(text=text, parse_mode='Markdown')

def get_balance():
    """Получает баланс USD через API и возвращает строку с информацией."""
    url = f"{BASE_API_URL}/partner/balance"
    response = requests.get(url, headers=API_HEADERS)
    if response.status_code == 200:
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            return "Ошибка: Некорректный ответ от API."
        balances = data.get("data", [])
        balance_usd = "Нет данных"
        for entry in balances:
            if entry.get("currency_code") == "USD":
                balance_usd = entry.get("balance", 0)
        return f"💰 *Ваш баланс (USD):* {balance_usd}"
    else:
        return f"Ошибка API: {response.status_code} {response.text}"

def get_offers():
    """Получает список офферов через API и возвращает краткую информацию."""
    url = f"{BASE_API_URL}/partner/offers"
    response = requests.get(url, headers=API_HEADERS)
    if response.status_code == 200:
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            return "Ошибка: Некорректный ответ от API."
        offers_list = data.get("data", [])
        meta = data.get("meta", {})
        if not offers_list:
            return "⚠️ Офферы не найдены."
        offers_text = "📋 *Список офферов:*\n"
        offers_text += f"Всего офферов: {meta.get('total_count', 'N/A')}\n"
        for offer in offers_list[:3]:
            name = offer.get("name", "N/A")
            offer_id = offer.get("id", "N/A")
            offers_text += f"🔹 {name} (ID: {offer_id})\n"
        if meta.get("total_count", 0) > 3:
            offers_text += "… и другие"
        return offers_text
    else:
        return f"Ошибка API: {response.status_code} {response.text}"

def run_telegram_bot():
    """Запускает Telegram-бота с использованием long polling."""
    updater = Updater(TELEGRAM_TOKEN)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CallbackQueryHandler(button_handler))
    updater.start_polling()
    updater.idle()

# ------------------------------
# Запуск Flask и Telegram-бота в отдельных потоках
# ------------------------------
def run_flask():
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

if __name__ == '__main__':
    flask_thread = Thread(target=run_flask)
    telegram_thread = Thread(target=run_telegram_bot)
    flask_thread.start()
    telegram_thread.start()
    flask_thread.join()
    telegram_thread.join()
