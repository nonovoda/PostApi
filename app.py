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
    # Получаем данные из запроса (GET-параметры или POST-тело)
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

    # Формирование сообщения по заданному формату
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
    """Endpoint для отправки тестового сообщения в Telegram."""
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
    """Endpoint для запроса статистики из ПП."""
    pp_stats_url = "https://cabinet.4rabetpartner.com/api/partner/stats"
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }
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
    Для этого мы обращаемся к API ПП и отправляем результат в Telegram.
    """
    # URL запроса к API ПП для получения баланса.
    # Проверьте документацию ПП — возможно, требуется другой путь или дополнительные параметры.
    pp_balance_url = "https://cabinet.4rabetpartner.com/api/partner/balance"
    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }
    response = requests.get(pp_balance_url, headers=headers)
    if response.status_code == 200:
        data = response.json()
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
            return jsonify({"error": "Ошибка отправки баланса в Telegram", "details": tg_response.text}), 500
    else:
        return jsonify({"error": "Ошибка запроса баланса из ПП", "details": response.text}), 500

if __name__ == '__main__':
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
