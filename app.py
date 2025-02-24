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
API_KEY = os.getenv("PP_API_KEY", "ВАШ_API_КЛЮЧ")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "ВАШ_CHAT_ID")
BASE_API_URL = "https://api.alanbase.com/v1"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-bot.onrender.com/webhook")
PORT = int(os.environ.get("PORT", 8000))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# Логирование конфигурационных переменных (скрываем часть ключей)
logger.debug(f"Конфигурация: PP_API_KEY = {API_KEY[:4]+'****' if API_KEY != 'ВАШ_API_КЛЮЧ' else API_KEY}, TELEGRAM_TOKEN = {TELEGRAM_TOKEN[:4]+'****' if TELEGRAM_TOKEN != 'ВАШ_ТОКЕН' else TELEGRAM_TOKEN}, TELEGRAM_CHAT_ID = {TELEGRAM_CHAT_ID}")

# ------------------------------
# Функция форматирования статистики
# ------------------------------
def format_statistics(response_json, period_label: str) -> str:
    data = response_json.get("data", [])
    meta = response_json.get("meta", {})
    
    if not data:
        return "⚠️ Статистика не найдена."
    
    stat = data[0]
    group_fields = stat.get("group_fields", [])
    date_info = group_fields[0].get("label") if group_fields else "Не указано"
    
    clicks = stat.get("click_count", "N/A")
    unique_clicks = stat.get("click_unique_count", "N/A")
    
    conversions = stat.get("conversions", {})
    confirmed = conversions.get("confirmed", {})
    pending = conversions.get("pending", {})
    hold = conversions.get("hold", {})
    rejected = conversions.get("rejected", {})
    total = conversions.get("total", {})
    
    message = (
        f"📊 *Статистика ({period_label})* 📊\n\n"
        f"🗓 Дата: *{date_info}*\n\n"
        f"🖱️ Клики: *{clicks}*\n"
        f"👥 Уникальные клики: *{unique_clicks}*\n\n"
        f"🔄 *Конверсии:*\n"
        f"✅ Подтвержденные: *{confirmed.get('count', 'N/A')}* (💰 {confirmed.get('payout', 'N/A')} USD)\n"
        f"⏳ Ожидающие: *{pending.get('count', 'N/A')}* (💰 {pending.get('payout', 'N/A')} USD)\n"
        f"🔒 В удержании: *{hold.get('count', 'N/A')}* (💰 {hold.get('payout', 'N/A')} USD)\n"
        f"❌ Отклоненные: *{rejected.get('count', 'N/A')}* (💰 {rejected.get('payout', 'N/A')} USD)\n"
        f"💰 Всего: *{total.get('count', 'N/A')}* (Сумма: {total.get('payout', 'N/A')} USD)\n\n"
        f"ℹ️ Страница: *{meta.get('page', 'N/A')}* / Последняя: *{meta.get('last_page', 'N/A')}* | Всего записей: *{meta.get('total_count', 'N/A')}*"
    )
    return message

# ------------------------------
# Инициализация Telegram-бота
# ------------------------------
application = Application.builder().token(TELEGRAM_TOKEN).build()

async def init_application():
    logger.debug("Инициализация и запуск Telegram-бота...")
    await application.initialize()
    await application.start()
    logger.debug("Бот успешно запущен!")

# ------------------------------
# FastAPI сервер для обработки вебхуков
# ------------------------------
app = FastAPI()

@app.post("/webhook")
async def telegram_webhook(request: Request):
    logger.debug("Получен запрос на /webhook")
    try:
        data = await request.json()
        logger.debug(f"Полученные данные: {data}")
    except Exception as e:
        logger.error(f"Ошибка при разборе JSON: {e}")
        return {"error": "Некорректный JSON"}, 400

    update = Update.de_json(data, application.bot)

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
    logger.debug("Отправка основного меню")
    await update.message.reply_text("Привет! Выберите команду:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = update.message.text
    logger.debug(f"Получено сообщение: {text}")

    # Заголовки для API-запросов (добавлен User-Agent)
    headers = {
        "API-KEY": API_KEY,
        "Content-Type": "application/json",
        "User-Agent": "TelegramBot/1.0 (compatible; Alanbase API integration)"
    }

    if text == "Получить статистику":
        period_keyboard = [["За час", "За день"], ["За прошлую неделю"], ["Назад"]]
        reply_markup = ReplyKeyboardMarkup(period_keyboard, resize_keyboard=True, one_time_keyboard=True)
        logger.debug("Отправка клавиатуры для выбора периода статистики")
        await update.message.reply_text("Выберите период статистики:", reply_markup=reply_markup)

    elif text in ["За час", "За день", "За прошлую неделю"]:
        now = datetime.now()
        period_label = text
        if text == "За час":
            date_from = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
            date_to = now.strftime("%Y-%m-%d %H:%M")
            group_by = "hour"
        elif text == "За день":
            selected_date = now.strftime("%Y-%m-%d 00:00")
            date_from = selected_date
            date_to = selected_date
            group_by = "day"
        elif text == "За прошлую неделю":
            weekday = now.weekday()
            last_monday = now - timedelta(days=weekday + 7)
            date_from = last_monday.replace(hour=0, minute=0).strftime("%Y-%m-%d %H:%M")
            last_sunday = last_monday + timedelta(days=6)
            date_to = last_sunday.replace(hour=23, minute=59).strftime("%Y-%m-%d %H:%M")
            group_by = "hour"

        params = {
            "group_by": group_by,
            "timezone": "Europe/Moscow",
            "date_from": date_from,
            "date_to": date_to,
            "currency_code": "USD"
        }
        logger.debug(f"Формирование запроса к {BASE_API_URL}/partner/statistic/common с параметрами: {params} и заголовками: {headers}")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{BASE_API_URL}/partner/statistic/common", headers=headers, params=params)
            logger.debug(f"Получен ответ API: {response.status_code} - {response.text}")
        except httpx.RequestError as exc:
            logger.error(f"Ошибка запроса к API: {exc}")
            await update.message.reply_text(f"⚠️ Ошибка запроса: {exc}")
            return

        if response.status_code == 200:
            try:
                data = response.json()
                message = format_statistics(data, period_label)
            except Exception as e:
                logger.error(f"Ошибка обработки JSON: {e}")
                message = "⚠️ Не удалось обработать ответ API."
        else:
            message = f"⚠️ Ошибка API {response.status_code}: {response.text}"
        
        await update.message.reply_text(message, parse_mode="Markdown")
    
    elif text == "📊 Статистика за день":
        now = datetime.now()
        selected_date = now.strftime("%Y-%m-%d 00:00")
        params = {
            "group_by": "day",
            "timezone": "Europe/Moscow",
            "date_from": selected_date,
            "date_to": selected_date,
            "currency_code": "USD"
        }
        logger.debug(f"Формирование запроса для 'Статистика за день' с параметрами: {params}")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{BASE_API_URL}/partner/statistic/common", headers=headers, params=params)
            logger.debug(f"Получен ответ API: {response.status_code} - {response.text}")
        except httpx.RequestError as exc:
            logger.error(f"Ошибка запроса к API: {exc}")
            await update.message.reply_text(f"⚠️ Ошибка запроса: {exc}")
            return

        if response.status_code == 200:
            try:
                data = response.json()
                message = format_statistics(data, "За день")
            except Exception as e:
                logger.error(f"Ошибка обработки JSON: {e}")
                message = "⚠️ Не удалось обработать ответ API."
        else:
            message = f"⚠️ Ошибка API {response.status_code}: {response.text}"
        
        await update.message.reply_text(message, parse_mode="Markdown")
    
    elif text == "🚀 Тестовая конверсия":
        await update.message.reply_text("🚀 Тестовая конверсия отправлена.")
    elif text == "🔍 Детальная статистика":
        await update.message.reply_text("🔍 Запрос детальной статистики отправлен.")
    elif text == "📈 Топ офферы":
        await update.message.reply_text("📈 Запрос списка топ офферов отправлен.")
    elif text == "🔄 Обновить данные":
        await update.message.reply_text("🔄 Данные обновлены!")
    elif text == "Назад":
        main_keyboard = [
            ["📊 Статистика за день", "🚀 Тестовая конверсия"],
            ["🔍 Детальная статистика", "📈 Топ офферы"],
            ["🔄 Обновить данные", "Получить статистику"]
        ]
        reply_markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True, one_time_keyboard=False)
        logger.debug("Возврат в главное меню")
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
    loop = asyncio.get_event_loop()
    loop.create_task(init_application())
    uvicorn.run(app, host="0.0.0.0", port=PORT)

