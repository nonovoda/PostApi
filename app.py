import os
import logging
import asyncio
from datetime import datetime
import httpx
from fastapi import FastAPI, Request, HTTPException
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ------------------------------
# Конфигурация
# ------------------------------
API_KEY = os.getenv("PP_API_KEY", "ВАШ_API_КЛЮЧ")  # Ключ API Alanbase
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "ВАШ_CHAT_ID")
BASE_API_URL = "https://api.alanbase.com/v1"  # Базовый URL API Alanbase
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-bot.onrender.com/webhook")
PORT = int(os.environ.get("PORT", 8000))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ------------------------------
# Инициализация Telegram-бота
# ------------------------------
application = Application.builder().token(TELEGRAM_TOKEN).build()

async def init_application():
    logger.info("Инициализация и запуск Telegram-бота...")
    await application.initialize()
    await application.start()
    logger.info("Бот успешно запущен!")

# ------------------------------
# FastAPI сервер для обработки вебхуков
# ------------------------------
app = FastAPI()

@app.post("/webhook")
async def telegram_webhook(request: Request):
    logger.info("Получен запрос на /webhook")
    try:
        data = await request.json()
        logger.info(f"Полученные данные: {data}")
    except Exception as e:
        logger.error(f"Ошибка при разборе JSON: {e}")
        raise HTTPException(status_code=400, detail="Некорректный JSON")

    update = Update.de_json(data, application.bot)

    # Если приложение не запущено – инициализируем его
    if not application.running:
        logger.warning("Telegram Application не запущено, выполняется инициализация...")
        await init_application()

    try:
        await application.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Ошибка обработки обновления: {e}")
        raise HTTPException(status_code=500, detail="Ошибка сервера")

# ------------------------------
# Обработчики команд и сообщений Telegram
# ------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["📊 Статистика за день", "🚀 Тестовая конверсия"],
        ["🔍 Детальная статистика", "📈 Топ офферы"],
        ["🔄 Обновить данные"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text("Привет! Выберите команду:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        text = update.message.text
    elif update.callback_query:
        text = update.callback_query.data
        await update.callback_query.answer()
    else:
        return

    # Заголовки для API-запросов – согласно документации, ключ передаётся через "API-KEY"
    headers = {
        "API-KEY": API_KEY,
        "Content-Type": "application/json"
    }

    if text == "📊 Статистика за день":
        now = datetime.now()
        date_from = now.strftime("%Y-%m-%d 00:00")
        date_to = now.strftime("%Y-%m-%d 23:59")

        # Обязательные параметры: group_by, timezone, date_from, date_to, currency_code
        params = {
            "group_by": "day",             # Допустимые значения: day, hour, offer, country, os, device, ...
            "timezone": "Europe/Moscow",   # Пример: Europe/Moscow
            "date_from": date_from,        # Формат: YYYY-MM-DD HH:mm
            "date_to": date_to,            # Формат: YYYY-MM-DD HH:mm
            "currency_code": "USD"         # Код валюты, в которую будут конвертированы платежи
        }

        logger.info(f"Отправка запроса к {BASE_API_URL}/partner/statistic/common с параметрами: {params}")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{BASE_API_URL}/partner/statistic/common", headers=headers, params=params)
            logger.info(f"Ответ API: {response.status_code} - {response.text}")
        except httpx.RequestError as exc:
            logger.error(f"Ошибка запроса к API: {exc}")
            await update.message.reply_text(f"⚠️ Ошибка запроса: {exc}")
            return

        if response.status_code == 200:
            try:
                data = response.json()
                # Форматируем ответ для Telegram
                message = "📊 Статистика за день:\n"
                for item in data.get("data", []):
                    message += f"Дата: {item['group_fields'][0]['label']}\n"
                    message += f"Клики: {item['click_count']}\n"
                    message += f"Конверсии: {item['conversions']['total']['count']}\n"
                    message += f"Выплаты: {item['conversions']['total']['payout']} USD\n\n"
            except Exception as e:
                logger.error(f"Ошибка обработки JSON: {e}")
                message = "⚠️ Не удалось обработать ответ API."
        else:
            message = f"⚠️ Ошибка API {response.status_code}: {response.text}"

        await update.message.reply_text(message)

    elif text == "🚀 Тестовая конверсия":
        # Реализация вызова API для тестовой конверсии (если предусмотрено) может быть добавлена здесь
        await update.message.reply_text("🚀 Тестовая конверсия отправлена.")
    elif text == "🔍 Детальная статистика":
        # Пример вызова API для детальной статистики
        await update.message.reply_text("🔍 Запрос детальной статистики отправлен.")
    elif text == "📈 Топ офферы":
        # Пример вызова API для получения списка топ офферов
        await update.message.reply_text("📈 Запрос списка топ офферов отправлен.")
    elif text == "🔄 Обновить данные":
        await update.message.reply_text("🔄 Данные обновлены!")
    else:
        await update.message.reply_text("Неизвестная команда. Попробуйте снова.")

# Регистрация обработчиков команд и сообщений
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))

# ------------------------------
# Основной запуск
# ------------------------------
if __name__ == "__main__":
    import uvicorn

    # Запуск Telegram-бота и FastAPI-сервера в одном процессе
    loop = asyncio.get_event_loop()
    loop.create_task(init_application())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
