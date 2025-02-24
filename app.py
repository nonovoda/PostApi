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
BASE_API_URL = "https://api.alanbase.com/v1"

# Заголовки для запросов к API
API_HEADERS = {
    "API-KEY": API_KEY,
    "Content-Type": "application/json"
}

# Настройка логирования для Telegram‑бота
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------
# Flask‑приложение для обработки HTTP‑запросов
# ------------------------------
app = Flask(__name__)

@app.route('/postback', methods=['GET', 'POST'])
def postback():
    """
    Принимает данные от партнёрской программы (POST/GET),
    проверяет API‑ключ и пересылает информацию в Telegram.
    """
    if request.method == 'POST':
        data = request.get_json() or request.form
    else:
        data = request.args

    if not data:
        return jsonify({"error": "Нет данных в запросе"}), 400

    if not data.get('api_key'):
        return jsonify({"error": "Не передан API‑ключ"}), 400
    if data.get('api_key') != API_KEY:
        return jsonify({"error": "Неверный API‑ключ"}), 403

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
    test_message = "Тестовое сообщение!\nПроверка работы бота."
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
    Endpoint для запроса общей статистики через API.
    Используется GET‑запрос к /partner/statistic/common.
    """
    url = f"{BASE_API_URL}/partner/statistic/common"
    response = requests.get(url, headers=API_HEADERS)
    if response.status_code == 200:
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            return jsonify({"error": "Неверный формат ответа от API", "raw_response": response.text}), 500

        meta = data.get("meta", {})
        stats_message = "📊 *Общая статистика:*\n"
        stats_message += f"Страница: {meta.get('page', 'N/A')}\n"
        stats_message += f"Записей на странице: {meta.get('per_page', 'N/A')}\n"
        stats_message += f"Всего записей: {meta.get('total_count', 'N/A')}\n"
        stats_message += f"Последняя страница: {meta.get('last_page', 'N/A')}\n"

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
        return jsonify({"error": "Ошибка получения данных из API", "details": response.text}), 500

@app.route('/wallet', methods=['GET'])
def wallet():
    """
    Endpoint для запроса информации о кошельке.
    Используется GET‑запрос к /partner/wallet.
    """
    url = f"{BASE_API_URL}/partner/wallet"
    response = requests.get(url, headers=API_HEADERS)
    if response.status_code == 200:
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            return jsonify({"error": "Неверный формат ответа от API", "raw_response": response.text}), 500

        # Предположим, что API возвращает данные о кошельке в ключе 'wallet'
        wallet_value = data.get("wallet")
        if wallet_value is None:
            wallet_message = "💰 *Кошелёк:*\nИнформация о кошельке не предоставлена API."
        else:
            wallet_message = f"💰 *Актуальный кошелёк:*\n{wallet_value}"

        telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": wallet_message,
            "parse_mode": "Markdown"
        }
        tg_response = requests.post(telegram_url, json=payload)
        if tg_response.status_code == 200:
            return jsonify({"status": "Информация о кошельке отправлена в Telegram"}), 200
        else:
            return jsonify({"error": "Ошибка отправки информации о кошельке в Telegram", "details": tg_response.text}), 500
    else:
        return jsonify({"error": "Ошибка запроса данных из API", "details": response.text}), 500

# ------------------------------
# Telegram Bot с inline‑кнопками
# ------------------------------
def start(update: Update, context: CallbackContext) -> None:
    """
    Обработчик команды /start.
    Отправляет сообщение с кнопками для выбора команды.
    """
    keyboard = [
        [InlineKeyboardButton("Статистика", callback_data='stats')],
        [InlineKeyboardButton("Кошелёк", callback_data='wallet')],
        [InlineKeyboardButton("Тест", callback_data='test')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Выберите команду:", reply_markup=reply_markup)

def button_handler(update: Update, context: CallbackContext) -> None:
    """
    Обработчик нажатий на inline‑кнопки.
    Выполняет соответствующий запрос к API в зависимости от выбранной команды.
    """
    query = update.callback_query
    query.answer()
    command = query.data
    text = ""

    if command == 'stats':
        url = f"{BASE_API_URL}/partner/statistic/common"
        response = requests.get(url, headers=API_HEADERS)
        if response.status_code == 200:
            try:
                data = response.json()
                meta = data.get("meta", {})
                text = ("📊 *Общая статистика:*\n" +
                        f"Страница: {meta.get('page', 'N/A')}\n" +
                        f"Записей: {meta.get('per_page', 'N/A')}\n" +
                        f"Всего: {meta.get('total_count', 'N/A')}\n" +
                        f"Последняя страница: {meta.get('last_page', 'N/A')}\n")
            except requests.exceptions.JSONDecodeError:
                text = "Ошибка декодирования ответа от API."
        else:
            text = f"Ошибка получения статистики: {response.text}"
    elif command == 'wallet':
        url = f"{BASE_API_URL}/partner/wallet"
        response = requests.get(url, headers=API_HEADERS)
        if response.status_code == 200:
            try:
                data = response.json()
                wallet_value = data.get("wallet")
                if wallet_value is None:
                    text = "💰 *Кошелёк:*\nИнформация о кошельке не предоставлена API."
                else:
                    text = f"💰 *Актуальный кошелёк:*\n{wallet_value}"
            except requests.exceptions.JSONDecodeError:
                text = "Ошибка декодирования ответа от API."
        else:
            text = f"Ошибка получения данных о кошельке: {response.text}"
    elif command == 'test':
        text = "Тестовое сообщение!\nПроверка работы бота."
    else:
        text = "Неизвестная команда."

    query.edit_message_text(text=text, parse_mode='Markdown')

def run_telegram_bot():
    """
    Запуск Telegram‑бота с использованием long polling.
    """
    updater = Updater(TELEGRAM_TOKEN)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CallbackQueryHandler(button_handler))
    updater.start_polling()
    updater.idle()

# ------------------------------
# Функция для запуска Flask‑приложения
# ------------------------------
def run_flask():
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)

# ------------------------------
# Основной блок: одновременный запуск Flask и Telegram‑бота
# ------------------------------
if __name__ == '__main__':
    flask_thread = Thread(target=run_flask)
    telegram_thread = Thread(target=run_telegram_bot)
    flask_thread.start()
    telegram_thread.start()
    flask_thread.join()
    telegram_thread.join()
