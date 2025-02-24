import os
import logging
import requests
from threading import Thread
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext

# ------------------------------
# Конфигурация и переменные окружения
# ------------------------------
API_KEY = os.getenv("PP_API_KEY", "5KH7dec1ptNTRmGVBLB1gmKXMz0EToJmLjUzO9mi7LYiON2S1Ri4n2166yqmcX2o")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "7643560524:AAGX9QB8C-STpWKxC0bqWFqzFIu0WmN8ses")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "802154146")

# Настройка логирования для Telegram бота
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------
# Flask-приложение для обработки HTTP-запросов
# ------------------------------
app = Flask(__name__)

@app.route('/postback', methods=['GET', 'POST'])
def postback():
    """
    Принимает данные от партнёрской программы (POST/GET),
    проверяет API ключ и пересылает информацию в Telegram.
    """
    # Извлекаем данные из запроса (JSON, form или query-параметры)
    if request.method == 'POST':
        data = request.get_json() or request.form
    else:
        data = request.args

    if not data:
        return jsonify({"error": "Нет данных в запросе"}), 400

    # Проверка API ключа
    if not data.get('api_key'):
        return jsonify({"error": "Не передан API ключ"}), 400
    if data.get('api_key') != API_KEY:
        return jsonify({"error": "Неверный API ключ"}), 403

    # Формирование сообщения с данными конверсии
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

    # Отправка сообщения в Telegram
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message_text,
        "parse_mode": "Markdown"
    }
    response = requests.post(telegram_url, json=payload)

    if response.status_code == 200:
        return jsonify({"status": "success"}), 200
    else:
        return jsonify({"error": "Ошибка при отправке сообщения в Telegram"}), 500

@app.route('/test', methods=['GET'])
def test():
    """
    Тестовый endpoint для отправки тестового сообщения в Telegram.
    """
    test_message = (
        "Тестовое сообщение!\n"
        "Проверка работы Telegram Postback Bot."
    )
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": test_message,
        "parse_mode": "Markdown"
    }
    response = requests.post(telegram_url, json=payload)
    if response.status_code == 200:
        return jsonify({"status": "Тестовое сообщение успешно отправлено"}), 200
    else:
        return jsonify({"error": "Ошибка при отправке тестового сообщения", "response": response.text}), 500

@app.route('/stats', methods=['GET'])
def stats():
    """
    Endpoint для запроса статистики из ПП и отправки её в Telegram.
    """
    pp_stats_url = "https://cabinet.4rabetpartner.com/api/partner/stats"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    response = requests.get(pp_stats_url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        stats_message = (
            "📊 *Статистика ПП:*\n"
            f"Конверсии: {data.get('conversions', 'N/A')}\n"
            f"Доход: {data.get('revenue', 'N/A')}\n"
            f"Баланс: {data.get('balance', 'N/A')}\n"
        )
        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": stats_message,
            "parse_mode": "Markdown"
        }
        tg_response = requests.post(telegram_url, json=payload)
        if tg_response.status_code == 200:
            return jsonify({"status": "Статистика отправлена в Telegram"}), 200
        else:
            return jsonify({"error": "Ошибка отправки данных в Telegram"}), 500
    else:
        return jsonify({"error": "Ошибка получения данных из ПП", "details": response.text}), 500

@app.route('/balance', methods=['GET'])
def balance():
    """
    Endpoint для запроса актуального баланса из ПП.
    Обрабатывает ответ API с проверкой корректности JSON.
    """
    pp_balance_url = "https://cabinet.4rabetpartner.com/api/partner/balance"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    response = requests.get(pp_balance_url, headers=headers)
    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        return jsonify({
            "error": "Неверный формат ответа от API, JSON не распарсен",
            "raw_response": response.text
        }), 500

    current_balance = data.get("balance", "N/A")
    message_text = (
        "💰 *Актуальный баланс:*\n"
        f"Баланс: {current_balance}\n"
    )
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message_text,
        "parse_mode": "Markdown"
    }
    tg_response = requests.post(telegram_url, json=payload)
    if tg_response.status_code == 200:
        return jsonify({"status": "Баланс отправлен в Telegram"}), 200
    else:
        return jsonify({
            "error": "Ошибка отправки баланса в Telegram",
            "details": tg_response.text
        }), 500

# ------------------------------
# Telegram Bot с inline-кнопками
# ------------------------------
def start(update: Update, context: CallbackContext) -> None:
    """
    Обработчик команды /start.
    Отправляет сообщение с кнопками для выбора команды.
    """
    keyboard = [
        [InlineKeyboardButton("Статистика", callback_data='stats')],
        [InlineKeyboardButton("Баланс", callback_data='balance')],
        [InlineKeyboardButton("Тест", callback_data='test')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Выберите команду:", reply_markup=reply_markup)

def button_handler(update: Update, context: CallbackContext) -> None:
    """
    Обработчик нажатий на inline-кнопки.
    В зависимости от выбранной кнопки отправляет запрос к API ПП.
    """
    query = update.callback_query
    query.answer()  # Подтверждаем получение callback-запроса
    command = query.data
    text = ""
    
    if command == 'stats':
        headers = {"Authorization": f"Bearer {API_KEY}"}
        response = requests.get("https://cabinet.4rabetpartner.com/api/partner/stats", headers=headers)
        if response.status_code == 200:
            data = response.json()
            text = (
                "📊 *Статистика ПП:*\n"
                f"Конверсии: {data.get('conversions', 'N/A')}\n"
                f"Доход: {data.get('revenue', 'N/A')}\n"
                f"Баланс: {data.get('balance', 'N/A')}\n"
            )
        else:
            text = f"Ошибка получения статистики: {response.text}"
    elif command == 'balance':
        headers = {"Authorization": f"Bearer {API_KEY}"}
        response = requests.get("https://cabinet.4rabetpartner.com/api/partner/balance", headers=headers)
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            text = f"Ошибка декодирования JSON: {response.text}"
        else:
            text = (
                "💰 *Актуальный баланс:*\n"
                f"Баланс: {data.get('balance', 'N/A')}\n"
            )
    elif command == 'test':
        text = "Тестовое сообщение!\nПроверка работы бота."
    else:
        text = "Неизвестная команда."
    
    query.edit_message_text(text=text, parse_mode='Markdown')

def run_telegram_bot():
    """
    Запуск Telegram-бота с использованием long polling.
    """
    updater = Updater(TELEGRAM_TOKEN)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CallbackQueryHandler(button_handler))
    updater.start_polling()
    updater.idle()

# ------------------------------
# Функция для запуска Flask-приложения
# ------------------------------
def run_flask():
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

# ------------------------------
# Основной блок запуска: одновременно запускаем Flask и Telegram-бота
# ------------------------------
if __name__ == '__main__':
    flask_thread = Thread(target=run_flask)
    telegram_thread = Thread(target=run_telegram_bot)
    flask_thread.start()
    telegram_thread.start()
    flask_thread.join()
    telegram_thread.join()
