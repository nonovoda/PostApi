import os
import logging
import asyncio
from datetime import datetime, timedelta
import httpx
from fastapi import FastAPI, Request
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ------------------------------
# Конфигурация
# ------------------------------
API_KEY = os.getenv("PP_API_KEY", "ВАШ_API_КЛЮЧ")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "ВАШ_CHAT_ID")
BASE_API_URL = "https://4rabet.api.alanbase.com/v1"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-bot.onrender.com/webhook")
PORT = int(os.environ.get("PORT", 8000))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)
logger.debug(f"Конфигурация: PP_API_KEY = {API_KEY[:4]+'****' if API_KEY != 'ВАШ_API_КЛЮЧ' else API_KEY}, "
             f"TELEGRAM_TOKEN = {TELEGRAM_TOKEN[:4]+'****' if TELEGRAM_TOKEN != 'ВАШ_ТОКЕН' else TELEGRAM_TOKEN}, "
             f"TELEGRAM_CHAT_ID = {TELEGRAM_CHAT_ID}")

# ------------------------------
# Создание экземпляра FastAPI
# ------------------------------
app = FastAPI()

def get_main_menu():
    # Главное меню с кнопками
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(text="📊 Получить статистику")],
            [KeyboardButton(text="🔗 ПП кабинет")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

def get_statistics_menu():
    # Подменю для выбора периода статистики
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(text="📅 За сегодня")],
            [KeyboardButton(text="🗓 За период"), KeyboardButton(text="📆 За месяц")],
            [KeyboardButton(text="↩️ Назад")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

# ------------------------------
# Инициализация Telegram-бота
# ------------------------------
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

async def init_telegram_app():
    logger.debug("Инициализация и запуск Telegram-бота...")
    await telegram_app.initialize()
    await telegram_app.start()
    logger.debug("Telegram-бот успешно запущен!")

# ------------------------------
# Обработка postback (GET и POST)
# ------------------------------
@app.api_route("/postback", methods=["GET", "POST"])
async def postback_handler(request: Request):
    if request.method == "GET":
        data = dict(request.query_params)
    else:
        try:
            data = await request.json()
        except Exception as e:
            logger.error(f"Ошибка при разборе JSON постбека: {e}")
            return {"error": "Некорректный JSON"}, 400

    logger.debug(f"Получены данные постбека: {data}")
    offer_id = data.get("offer_id", "N/A")
    sub_id2 = data.get("sub_id2", "N/A")
    goal = data.get("goal", "N/A")
    revenue = data.get("revenue", "N/A")
    currency = data.get("currency", "USD")
    status = data.get("status", "N/A")
    sub_id4 = data.get("sub_id4", "N/A")
    sub_id5 = data.get("sub_id5", "N/A")
    conversion_date = data.get("conversion_date", "N/A")

    message = (
        "🔔 <b>Новая конверсия!</b>\n\n"
        f"<b>📌 Оффер:</b> <i>{offer_id}</i>\n"
        f"<b>🛠 Подход:</b> <i>{sub_id2}</i>\n"
        f"<b>📊 Тип конверсии:</b> <i>{goal}</i>\n"
        f"<b>💰 Выплата:</b> <i>{revenue} {currency}</i>\n"
        f"<b>⚙️ Статус конверсии:</b> <i>{status}</i>\n"
        f"<b>🎯 Кампания:</b> <i>{sub_id4}</i>\n"
        f"<b>🎯 Адсет:</b> <i>{sub_id5}</i>\n"
        f"<b>⏰ Время конверсии:</b> <i>{conversion_date}</i>"
    )

    try:
        await telegram_app.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode="HTML",
            reply_markup=get_main_menu()
        )
        logger.debug("Постбек успешно отправлен в Telegram")
    except Exception as e:
        logger.error(f"Ошибка отправки постбека в Telegram: {e}")
        return {"error": "Не удалось отправить сообщение"}, 500

    return {"status": "ok"}

# ------------------------------
# Обработчик команды /start
# ------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Задержка 1 секунда перед удалением предыдущего сообщения
    await asyncio.sleep(1)
    last_msg_id = context.user_data.get("last_bot_message_id")
    if last_msg_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_msg_id)
        except Exception as e:
            logger.debug(f"Не удалось удалить предыдущее сообщение бота: {e}")
    main_keyboard = get_main_menu()
    logger.debug("Отправка главного меню")
    text = "Привет! Выберите команду:"
    sent_msg = await update.message.reply_text(text, reply_markup=main_keyboard, parse_mode="HTML")
    context.user_data["last_bot_message_id"] = sent_msg.message_id

# ------------------------------
# Обработчик кнопок (универсальный MessageHandler)
# ------------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    # Задержка 1 секунда перед удалением входящего сообщения
    await asyncio.sleep(1)
    try:
        await update.message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение пользователя: {e}")

    # Задержка 1 секунда перед удалением предыдущего сообщения бота
    await asyncio.sleep(1)
    last_msg_id = context.user_data.get("last_bot_message_id")
    if last_msg_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_msg_id)
        except Exception as e:
            logger.debug(f"Не удалось удалить предыдущее сообщение бота: {e}")

    text = update.message.text.strip()
    logger.debug(f"Получено сообщение: {text}")

    if text == "📊 Получить статистику":
        reply_markup = get_statistics_menu()
        sent_msg = await update.message.reply_text("Выберите период статистики:", reply_markup=reply_markup, parse_mode="HTML")
        context.user_data["last_bot_message_id"] = sent_msg.message_id
        return

    if text == "🔗 ПП кабинет":
        sent_msg = await update.message.reply_text("🔗 Перейдите в ПП кабинет: https://cabinet.4rabetpartner.com/statistics")
        context.user_data["last_bot_message_id"] = sent_msg.message_id
        return

    if text == "↩️ Назад":
        reply_markup = get_main_menu()
        sent_msg = await update.message.reply_text("Возврат в главное меню:", reply_markup=reply_markup, parse_mode="HTML")
        context.user_data["last_bot_message_id"] = sent_msg.message_id
        return

    sent_msg = await update.message.reply_text("Неизвестная команда. Попробуйте снова.", parse_mode="HTML", reply_markup=get_main_menu())
    context.user_data["last_bot_message_id"] = sent_msg.message_id

# ------------------------------
# Регистрация обработчиков Telegram
# ------------------------------
telegram_app.add_handler(CommandHandler("start", start_command))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))

# ------------------------------
# Основной запуск приложения
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    loop = asyncio.get_event_loop()
    loop.create_task(init_telegram_app())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
