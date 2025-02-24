import os
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# Загружаем переменные окружения
API_KEY = os.getenv("PP_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

@app.route('/postback', methods=['GET', 'POST'])
def postback():
    # Получаем данные из запроса: для GET — из query-параметров, для POST — из JSON или form
    if request.method == 'POST':
        data = request.get_json() or request.form
    else:
        data = request.args

    if not data:
        return jsonify({"error": "Нет данных в запросе"}), 400

    # Проверка наличия и корректности API ключа
    if not data.get('api_key'):
        return jsonify({"error": "Не передан API ключ"}), 400
    if data.get('api_key') != API_KEY:
        return jsonify({"error": "Неверный API ключ"}), 403

    # Формируем сообщение по требуемому формату с подстановкой макросов
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
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
