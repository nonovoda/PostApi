import os
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# Загружаем конфигурацию из переменных окружения (Railway использует переменные окружения)
API_KEY = os.getenv("PP_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

@app.route('/postback', methods=['POST'])
def postback():
    data = request.json
    if not data:
        return jsonify({"error": "Нет данных в теле запроса"}), 400

    # Проверяем API ключ
    if 'api_key' not in data or data['api_key'] != API_KEY:
        return jsonify({"error": "Неверный API ключ"}), 403

    # Формируем сообщение для Telegram
    message_text = "📩 *Получен новый постбек:*\n"
    for key, value in data.items():
        if key != "api_key":
            message_text += f"📌 *{key}*: `{value}`\n"

    # Отправляем сообщение в Telegram
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 5000)))
