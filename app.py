import os
import logging
import asyncio
from datetime import datetime, timedelta
import httpx
from fastapi import FastAPI, Request
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.helpers import escape_markdown

# ------------------------------
# Конфигурация
# ------------------------------
API_KEY = os.getenv("PP_API_KEY", "ВАШ_API_КЛЮЧ")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "ВАШ_CHAT_ID")
# Новый URL API (сообщили в поддержке Alanbase)
BASE_API_URL = "https://4rabet.api.alanbase.com/v1"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://your-bot.onrender.com/webhook")
PORT = int(os.environ.get("PORT", 8000))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)
logger.debug(f"Конфигурация: PP_API_KEY = {API_KEY[:4]+'****' if API_KEY != 'ВАШ_API_КЛЮЧ' else API_KEY}, TELEGRAM_TOKEN = {TELEGRAM_TOKEN[:4]+'****' if TELEGRAM_TOKEN != 'ВАШ_ТОКЕН' else TELEGRAM_TOKEN}, TELEGRAM_CHAT_ID = {TELEGRAM_CHAT_ID}")

# ------------------------------
# Создание экземпляра FastAPI
# ------------------------------
app = FastAPI()

# ------------------------------
# Функция форматирования статистики
# ------------------------------
async def format_statistics(response_json, period_label: str) -> str:
    data = response_json.get("data", [])
    if not data:
        return "⚠️ *Статистика не найдена.*"
    stat = data[0]
    group_fields = stat.get("group_fields", [])
    date_info = group_fields[0].get("label") if group_fields else "Не указано"
    clicks = stat.get("click_count", "N/A")
    unique_clicks = stat.get("click_unique_count", "N/A")
    confirmed = stat.get("conversions", {}).get("confirmed", {})
message = (
    f"**📊 Статистика ({period_label})**\n\n"
    f"**Дата:** _{date_info}_\n\n"
    f"**Клики:**\n"
    f"• **Всего:** _{clicks}_\n"
    f"• **Уникальные:** _{unique_clicks}_\n\n"
    f"**Конверсии:**\n"
    f"• **Регистрация:** _{reg.get('count', 'N/A')}_ (💰 _{reg.get('payout', 'N/A')} USD_)\n"
    f"• **Депозиты:** _{dep.get('count', 'N/A')}_ (💰 _{dep.get('payout', 'N/A')} USD_)\n"
    f"**Доход:** _{confirmed.get('income', 'N/A')} USD_"
)
    return message

async def format_offers(response_json) -> str:
    offers = response_json.get("data", [])
    meta = response_json.get("meta", {})
    if not offers:
        return "⚠️ *Офферы не найдены.*"
    message = "**📈 Топ офферы:**\n\n"
    for offer in offers:
        message += f"• **ID:** {offer.get('id')} | **Название:** {offer.get('name')}\n"
    return message

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
# Обработка постбеков от ПП
# ------------------------------
async def postback_handler(request: Request):
    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"Ошибка при разборе JSON постбека: {e}")
        return {"error": "Некорректный JSON"}, 400

    logger.debug(f"Получен постбек: {data}")
    # Извлекаем поля и формируем сообщение (без изменений)
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
        "🔔 **Новая конверсия!**\n\n"
        f"**📌 Оффер:** _{offer_id}_\n"
        f"**🛠 Подход:** _{sub_id2}_\n"
        f"**📊 Тип конверсии:** _{goal}_\n"
        f"**💰 Выплата:** _{revenue} {currency}_\n"
        f"**⚙️ Статус конверсии:** _{status}_\n"
        f"**🎯 Кампания:** _{sub_id4}_\n"
        f"**🎯 Адсет:** _{sub_id5}_\n"
        f"**⏰ Время конверсии:** _{conversion_date}_"
    )

    try:
        escaped_message = escape_markdown(message, version=2)
        await telegram_app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=escaped_message, parse_mode="MarkdownV2")
        logger.debug("Постбек успешно отправлен в Telegram")
    except Exception as e:
        logger.error(f"Ошибка отправки постбека в Telegram: {e}")
        return {"error": "Не удалось отправить сообщение"}, 500

    return {"status": "ok"}

# ------------------------------
# Единый эндпоинт для входящих запросов (Telegram и постбеки)
# ------------------------------
@app.post("/webhook")
async def webhook_handler(request: Request):
    logger.debug("Получен запрос на /webhook")
    try:
        data = await request.json()
        logger.debug(f"Полученные данные: {data}")
    except Exception as e:
        logger.error(f"Ошибка при разборе JSON: {e}")
        return {"error": "Некорректный JSON"}, 400

    if "update_id" in data:
        update = Update.de_json(data, telegram_app.bot)
        if not telegram_app.running:
            logger.warning("Telegram Application не запущено, выполняется инициализация...")
            await init_telegram_app()
        try:
            await telegram_app.process_update(update)
            return {"status": "ok"}
        except Exception as e:
            logger.error(f"Ошибка обработки обновления: {e}")
            return {"error": "Ошибка сервера"}, 500
    else:
        return await postback_handler(request)

# ------------------------------
# Обработчики команд Telegram
# ------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    main_keyboard = [
        [KeyboardButton(text="Получить статистику")],
        [KeyboardButton(text="📈 Топ офферы")],
        [KeyboardButton(text="🔄 Обновить данные")]
    ]
    reply_markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True, one_time_keyboard=False)
    logger.debug("Отправка основного меню")
    text = "Привет! Выберите команду:"
    escaped_text = escape_markdown(text, version=2)
    await update.message.reply_text(escaped_text, reply_markup=reply_markup, parse_mode="MarkdownV2")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = update.message.text
    logger.debug(f"Получено сообщение: {text}")

    headers = {
        "API-KEY": API_KEY,
        "Content-Type": "application/json",
        "User-Agent": "TelegramBot/1.0 (compatible; Alanbase API integration)"
    }
    now = datetime.now()

    if text == "Получить статистику":
        period_keyboard = [
            [KeyboardButton(text="За час"), KeyboardButton(text="За день")],
            [KeyboardButton(text="За прошлую неделю")],
            [KeyboardButton(text="Назад")]
        ]
        reply_markup = ReplyKeyboardMarkup(period_keyboard, resize_keyboard=True, one_time_keyboard=True)
        logger.debug("Отправка подменю для выбора периода статистики")
        await update.message.reply_text("Выберите период статистики:", reply_markup=reply_markup)
    
   elif text == "За час":
    # Для "За час" устанавливаем дату как текущий час (начало часа)
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    date_from = current_hour.strftime("%Y-%m-%d %H:%M")
    date_to = date_from  # API требует равенства для группировки по часу
    group_by = "hour"
elif text == "За день":
    selected_date = now.strftime("%Y-%m-%d")
    date_from = f"{selected_date} 00:00"
    date_to = f"{selected_date} 00:00"  # для группировки по дню
    group_by = "day"
elif text == "За прошлую неделю":
    # Группируем по дням – для каждого дня запрос формируется отдельно (здесь пример запроса за первый день прошлой недели)
    last_week_start = (now - timedelta(days=now.weekday() + 7)).replace(hour=0, minute=0, second=0, microsecond=0)
    date_from = last_week_start.strftime("%Y-%m-%d %H:%M")
    date_to = date_from  # для группировки по дню
    group_by = "day"
        
        params = {
            "group_by": group_by,
            "timezone": "Europe/Moscow",
            "date_from": date_from,
            "date_to": date_to,
            "currency_code": "USD"
        }
        full_url = str(httpx.URL(f"{BASE_API_URL}/partner/statistic/common").copy_merge_params(params))
        logger.debug(f"Полный URL запроса: {full_url}")
        logger.debug(f"Отправка запроса к {BASE_API_URL}/partner/statistic/common с заголовками: {headers}")
        start_time = datetime.now()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{BASE_API_URL}/partner/statistic/common", headers=headers, params=params)
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.debug(f"Ответ API получен за {elapsed:.2f} сек: {response.status_code} - {response.text}")
        except httpx.RequestError as exc:
            logger.error(f"Ошибка запроса к API: {exc}")
            await update.message.reply_text(f"⚠️ Ошибка запроса: {exc}")
            return

        if response.status_code == 200:
            try:
                data = response.json()
                message = await format_statistics(data, period_label)
            except Exception as e:
                logger.error(f"Ошибка обработки JSON: {e}")
                message = "⚠️ Не удалось обработать ответ API."
        else:
            message = f"⚠️ Ошибка API {response.status_code}: {response.text}"
        
        escaped_message = escape_markdown(message, version=2)
        await update.message.reply_text(escaped_message, parse_mode="MarkdownV2")
    
    elif text == "📈 Топ офферы":
        params = {
            "is_avaliable": 1,
            "page": 1,
            "per_page": 10
        }
        logger.debug(f"Формирование запроса к {BASE_API_URL}/partner/offers с параметрами: {params}")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{BASE_API_URL}/partner/offers", headers=headers, params=params)
            logger.debug(f"Получен ответ API: {response.status_code} - {response.text}")
        except httpx.RequestError as exc:
            logger.error(f"Ошибка запроса к API: {exc}")
            await update.message.reply_text(f"⚠️ Ошибка запроса: {exc}")
            return
        
        if response.status_code == 200:
            try:
                data = response.json()
                message = await format_offers(data)
            except Exception as e:
                logger.error(f"Ошибка обработки JSON: {e}")
                message = "⚠️ Не удалось обработать ответ API."
        else:
            message = f"⚠️ Ошибка API {response.status_code}: {response.text}"
        escaped_message = escape_markdown(message, version=2)
        await update.message.reply_text(escaped_message, parse_mode="MarkdownV2")
    
    elif text == "🔄 Обновить данные":
        await update.message.reply_text("🔄 Данные обновлены!")
    
    elif text == "Назад":
        main_keyboard = [
            [KeyboardButton(text="Получить статистику")],
            [KeyboardButton(text="📈 Топ офферы")],
            [KeyboardButton(text="🔄 Обновить данные")]
        ]
        reply_markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True, one_time_keyboard=False)
        logger.debug("Возврат в главное меню")
        await update.message.reply_text("Возврат в главное меню:", reply_markup=reply_markup)
    
    else:
        await update.message.reply_text("Неизвестная команда. Попробуйте снова.")

# ------------------------------
# Регистрация обработчиков Telegram
# ------------------------------
telegram_app.add_handler(CommandHandler("start", start_command))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))

# ------------------------------
# Основной запуск
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    loop = asyncio.get_event_loop()
    loop.create_task(init_telegram_app())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
