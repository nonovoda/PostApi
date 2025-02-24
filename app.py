import os
import logging
import asyncio
from datetime import datetime, timedelta
import httpx
from fastapi import FastAPI, Request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ------------------------------
# Конфигурация
# ------------------------------
API_KEY = os.getenv("PP_API_KEY", "ВАШ_API_КЛЮЧ")  # Согласно документации – передаётся в заголовке "API-KEY"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "ВАШ_CHAT_ID")
BASE_API_URL = "https://api.alanbase.com/v1"  # URL API Alanbase
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
        return {"error": "Некорректный JSON"}, 400

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
        return {"error": "Ошибка сервера"}, 500

# ------------------------------
# Обработчики команд и сообщений Telegram
# ------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["📊 Статистика за день", "🚀 Тестовая конверсия"],
        ["🔍 Детальная статистика", "📈 Топ офферы"],
        ["🔄 Обновить данные", "Получить статистику"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_text("Привет! Выберите команду:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        text = update.message.text
    else:
        return

    # Заголовки для API-запросов – согласно документации, ключ передаётся через "API-KEY"
    headers = {
        "API-KEY": API_KEY,
        "Content-Type": "application/json"
    }

    # Если выбрана кнопка для первоначального запроса статистики с выбором периода
    if text == "Получить статистику":
        # Отправляем пользователю клавиатуру с вариантами периодов
        period_keyboard = [["За час", "За день"], ["Назад"]]
        reply_markup = ReplyKeyboardMarkup(period_keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("Выберите период статистики:", reply_markup=reply_markup)
    
    # Обработка выбора периода статистики
    elif text == "За час" or text == "За день":
        now = datetime.now()
        if text == "За час":
            # Статистика за последний час (группировка по часу)
            date_from = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
            date_to = now.strftime("%Y-%m-%d %H:%M")
            group_by = "hour"
        elif text == "За день":
            # Статистика за день (группировка по дню, API может требовать одинаковых значений)
            selected_date = now.strftime("%Y-%m-%d 00:00")
            date_from = selected_date
            date_to = selected_date
            group_by = "day"
        
        params = {
            "group_by": group_by,
            "timezone": "Europe/Moscow",
            "date_from": date_from,
            "date_to": date_to,
            "currency_code": "USD"
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
                message = f"📊 Статистика ({text}):\n{data}"
            except Exception as e:
                logger.error(f"Ошибка обработки JSON: {e}")
                message = "⚠️ Не удалось обработать ответ API."
        else:
            message = f"⚠️ Ошибка API {response.status_code}: {response.text}"
        
        await update.message.reply_text(message)

    elif text == "📊 Статистика за день":
        now = datetime.now()
        # Пример запроса без выбора периода (фиксированная статистика за день)
        selected_date = now.strftime("%Y-%m-%d 00:00")
        params = {
            "group_by": "day",
            "timezone": "Europe/Moscow",
            "date_from": selected_date,
            "date_to": selected_date,
            "currency_code": "USD"
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
                message = f"📊 Статистика за день:\n{data}"
            except Exception as e:
                logger.error(f"Ошибка обработки JSON: {e}")
                message = "⚠️ Не удалось обработать ответ API."
        else:
            message = f"⚠️ Ошибка API {response.status_code}: {response.text}"
        
        await update.message.reply_text(message)
    
    elif text == "🚀 Тестовая конверсия":
        await update.message.reply_text("🚀 Тестовая конверсия отправлена.")
    elif text == "🔍 Детальная статистика":
        await update.message.reply_text("🔍 Запрос детальной статистики отправлен.")
    elif text == "📈 Топ офферы":
        await update.message.reply_text("📈 Запрос списка топ офферов отправлен.")
    elif text == "🔄 Обновить данные":
        await update.message.reply_text("🔄 Данные обновлены!")
    elif text == "Назад":
        # Возврат к основному меню
        main_keyboard = [
            ["📊 Статистика за день", "🚀 Тестовая конверсия"],
            ["🔍 Детальная статистика", "📈 Топ офферы"],
            ["🔄 Обновить данные", "Получить статистику"]
        ]
        reply_markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True, one_time_keyboard=False)
        await update.message.reply_text("Возврат в главное меню:", reply_markup=reply_markup)
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
