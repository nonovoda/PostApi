import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
API_KEY = os.getenv("PP_API_KEY")

# URL-адреса для запросов к API ПП (уточните их согласно документации ПП)
STATS_URL = "https://cabinet.4rabetpartner.com/api/partner/stats"
BALANCE_URL = "https://cabinet.4rabetpartner.com/api/partner/balance"

def start(update: Update, context: CallbackContext) -> None:
    """Обработчик команды /start. Отправляет сообщение с кнопками для выбора команды."""
    keyboard = [
        [InlineKeyboardButton("Статистика", callback_data='stats')],
        [InlineKeyboardButton("Баланс", callback_data='balance')],
        [InlineKeyboardButton("Тест", callback_data='test')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Выберите команду:", reply_markup=reply_markup)

def button_handler(update: Update, context: CallbackContext) -> None:
    """Обработчик нажатий на inline кнопки."""
    query = update.callback_query
    query.answer()  # подтверждаем получение callback-запроса
    command = query.data
    text = ""
    
    if command == 'stats':
        headers = {"Authorization": f"Bearer {API_KEY}"}
        response = requests.get(STATS_URL, headers=headers)
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
        response = requests.get(BALANCE_URL, headers=headers)
        if response.status_code == 200:
            data = response.json()
            text = (
                "💰 *Актуальный баланс:*\n"
                f"Баланс: {data.get('balance', 'N/A')}\n"
            )
        else:
            text = f"Ошибка получения баланса: {response.text}"
    elif command == 'test':
        text = "Тестовое сообщение!\nПроверка работы бота."
    else:
        text = "Неизвестная команда."
    
    query.edit_message_text(text=text, parse_mode='Markdown')

def main() -> None:
    """Основная функция запуска бота."""
    updater = Updater(TELEGRAM_TOKEN)
    dispatcher = updater.dispatcher

    # Обработчик команды /start
    dispatcher.add_handler(CommandHandler("start", start))
    # Обработчик нажатий на inline кнопки
    dispatcher.add_handler(CallbackQueryHandler(button_handler))

    # Запуск бота (Long Polling)
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
