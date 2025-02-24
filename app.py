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

# Заголовки для запросов к API (с User-Agent)
API_HEADERS = {
    "API-KEY": API_KEY,
    "Content-Type": "application/json",
    "User-Agent": "AlanbaseTelegramBot/1.0"
}

# ------------------------------
# Логирование
# ------------------------------
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.debug("Бот запускается с токеном: %s", TELEGRAM_TOKEN)

# ------------------------------
# Flask API
# ------------------------------
app = Flask(__name__)

@app.route('/postback', methods=['GET', 'POST'])
def postback():
    logger.debug("Получен запрос /postback: %s", request.data)
    data = request.get_json() or request.args
    if not data:
        logger.error("Нет данных в запросе /postback")
        return jsonify({"error": "Нет данных в запросе"}), 400

    if not data.get('api_key'):
        logger.error("Не передан API-ключ в /postback")
        return jsonify({"error": "Не передан API-ключ"}), 400
    if data.get('api_key') != API_KEY:
        logger.error("Неверный API-ключ в /postback: %s", data.get('api_key'))
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
    logger.info("Отправляю сообщение в Telegram: %s", message_text)
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message_text, "parse_mode": "Markdown"}
    requests.post(telegram_url, json=payload)
    return jsonify({"status": "success"}), 200

@app.route('/test', methods=['GET'])
def test():
    logger.debug("Получен запрос /test")
    test_message = "Тестовое сообщение!\nПроверка работы бота."
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": test_message, "parse_mode": "Markdown"}
    requests.post(telegram_url, json=payload)
    return jsonify({"status": "Тестовое сообщение успешно отправлено"}), 200

@app.route('/stats', methods=['GET'])
def stats():
    logger.debug("Получен запрос /stats")
    url = f"{BASE_API_URL}/partner/statistic/common"
    response = requests.get(url, headers=API_HEADERS)
    logger.debug("Статистика, статус: %s, ответ: %s", response.status_code, response.text)
    if response.status_code == 200:
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            logger.error("Неверный формат ответа от API в /stats: %s", response.text)
            return jsonify({"error": "Неверный формат ответа от API", "raw_response": response.text}), 500

        meta = data.get("meta", {})
        stats_message = (
            "📊 *Общая статистика:*\n"
            f"Страница: {meta.get('page', 'N/A')}\n"
            f"Записей на странице: {meta.get('per_page', 'N/A')}\n"
            f"Всего записей: {meta.get('total_count', 'N/A')}\n"
            f"Последняя страница: {meta.get('last_page', 'N/A')}\n"
        )
        logger.info("Статистика: %s", stats_message)
        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": stats_message, "parse_mode": "Markdown"}
        requests.post(telegram_url, json=payload)
        return jsonify({"status": "Статистика отправлена в Telegram"}), 200
    else:
        logger.error("Ошибка получения статистики: %s", response.text)
        return jsonify({"error": "Ошибка получения данных из API", "details": response.text}), 500

@app.route('/offers', methods=['GET'])
def offers():
    logger.debug("Получен запрос /offers")
    url = f"{BASE_API_URL}/partner/offers"
    response = requests.get(url, headers=API_HEADERS)
    logger.debug("Офферы, статус: %s, ответ: %s", response.status_code, response.text)
    if response.status_code == 200:
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            logger.error("Неверный формат ответа от API в /offers: %s", response.text)
            return jsonify({"error": "Неверный формат ответа от API", "raw_response": response.text}), 500

        offers_list = data.get("data", [])
        meta = data.get("meta", {})
        if not offers_list:
            offers_text = "⚠️ Офферы не найдены."
        else:
            offers_text = "📋 *Список офферов:*\n"
            offers_text += f"Всего офферов: {meta.get('total_count', 'N/A')}\n"
            for offer in offers_list[:3]:
                name = offer.get("name", "N/A")
                offer_id = offer.get("id", "N/A")
                offers_text += f"🔹 {name} (ID: {offer_id})\n"
            if meta.get("total_count", 0) > 3:
                offers_text += "… и другие"
        logger.info("Офферы: %s", offers_text)
        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": offers_text, "parse_mode": "Markdown"}
        requests.post(telegram_url, json=payload)
        return jsonify({"status": "Офферы отправлены в Telegram"}), 200
    else:
        logger.error("Ошибка получения офферов: %s", response.text)
        return jsonify({"error": "Ошибка получения данных из API", "details": response.text}), 500

@app.route('/conversions', methods=['GET'])
def conversions():
    logger.debug("Получен запрос /conversions")
    # Для теста используем фиксированные параметры
    params = {
        "timezone": "Europe/Moscow",
        "date_from": "2023-01-01 00:00:00",
        "date_to": "2023-01-02 00:00:00"
    }
    url = f"{BASE_API_URL}/partner/statistic/conversions"
    response = requests.get(url, headers=API_HEADERS, params=params)
    logger.debug("Конверсии, статус: %s, ответ: %s", response.status_code, response.text)
    if response.status_code == 200:
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            logger.error("Неверный формат ответа от API в /conversions: %s", response.text)
            return jsonify({"error": "Неверный формат ответа от API", "raw_response": response.text}), 500

        meta = data.get("meta", {})
        total = meta.get("total_count", "N/A")
        conversions_message = f"🔄 *Конверсии за период:*\nВсего конверсий: {total}"
        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": conversions_message, "parse_mode": "Markdown"}
        requests.post(telegram_url, json=payload)
        return jsonify({"status": "Конверсии отправлены в Telegram"}), 200
    else:
        logger.error("Ошибка получения конверсий: %s", response.text)
        return jsonify({"error": "Ошибка получения данных из API", "details": response.text}), 500

# ------------------------------
# Telegram-бот с inline-кнопками
# ------------------------------
def start(update: Update, context: CallbackContext) -> None:
    logger.debug("Получена команда /start от пользователя: %s", update.effective_user.username)
    keyboard = [
        [InlineKeyboardButton("Статистика", callback_data='stats')],
        [InlineKeyboardButton("Конверсии", callback_data='conversions')],
        [InlineKeyboardButton("Офферы", callback_data='offers')],
        [InlineKeyboardButton("Тест", callback_data='test')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Выберите команду:", reply_markup=reply_markup)

def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    logger.debug("Нажата кнопка: %s", query.data)
    query.answer()
    command = query.data
    text = ""

    if command == 'stats':
        text = "Запрос статистики отправлен."
    elif command == 'conversions':
        text = get_conversions()
    elif command == 'offers':
        text = get_offers()
    elif command == 'test':
        text = "Тестовое сообщение отправлено."
    else:
        text = "Неизвестная команда."

    logger.debug("Ответ бота: %s", text)
    query.edit_message_text(text=text, parse_mode='Markdown')

def get_conversions():
    """Получает данные по конверсиям через API и возвращает строку с информацией."""
    params = {
        "timezone": "Europe/Moscow",
        "date_from": "2023-01-01 00:00:00",
        "date_to": "2023-01-02 00:00:00"
    }
    url = f"{BASE_API_URL}/partner/statistic/conversions"
    response = requests.get(url, headers=API_HEADERS, params=params)
    if response.status_code == 200:
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            logger.error("Ошибка декодирования ответа в get_conversions: %s", response.text)
            return "Ошибка: Некорректный ответ от API."
        meta = data.get("meta", {})
        total = meta.get("total_count", "N/A")
        return f"🔄 *Конверсии за выбранный период:*\nВсего конверсий: {total}"
    else:
        logger.error("Ошибка API в get_conversions: %s %s", response.status_code, response.text)
        return f"Ошибка API: {response.status_code} {response.text}"

def get_offers():
    url = f"{BASE_API_URL}/partner/offers"
    response = requests.get(url, headers=API_HEADERS)
    if response.status_code == 200:
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            logger.error("Ошибка декодирования ответа в get_offers: %s", response.text)
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
        logger.error("Ошибка API в get_offers: %s %s", response.status_code, response.text)
        return f"Ошибка API: {response.status_code} {response.text}"

def run_telegram_bot():
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
