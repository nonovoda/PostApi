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
logger.debug(f"Конфигурация: PP_API_KEY = {API_KEY[:4]+'****' if API_KEY != 'ВАШ_API_КЛЮЧ' else API_KEY}, TELEGRAM_TOKEN = {TELEGRAM_TOKEN[:4]+'****' if TELEGRAM_TOKEN != 'ВАШ_ТОКЕН' else TELEGRAM_TOKEN}, TELEGRAM_CHAT_ID = {TELEGRAM_CHAT_ID}")

# ------------------------------
# Функция форматирования статистики (общей)
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
# Функция форматирования офферов (топ офферы)
# ------------------------------
def format_offers(response_json) -> str:
    offers = response_json.get("data", [])
    meta = response_json.get("meta", {})
    if not offers:
        return "⚠️ Офферы не найдены."
    message = "📈 *Топ офферы:*\n\n"
    for offer in offers:
        message += f"• *ID:* {offer.get('id')} | *Название:* {offer.get('name')}\n"
    message += f"\nℹ️ Страница: {meta.get('page', 'N/A')} / Всего: {meta.get('total_count', 'N/A')}"
    return message

# ------------------------------
# Функция форматирования конверсии (тестовая конверсия)
# ------------------------------
def format_conversion(response_json) -> str:
    data = response_json.get("data", [])
    if not data:
        return "⚠️ Конверсии не найдены."
    conv = data[0]
    message = (
        f"🚀 *Тестовая конверсия:*\n\n"
        f"ID: {conv.get('conversion_id', 'N/A')}\n"
        f"Статус: {conv.get('status', 'N/A')}\n"
        f"Причина отклонения: {conv.get('decline_reason', 'N/A')}\n"
        f"Дата конверсии: {conv.get('conversion_datetime', 'N/A')}\n"
        f"Модель оплаты: {conv.get('payment_model', 'N/A')}\n"
        f"Платёж: {conv.get('payout', 'N/A')} {conv.get('payout_currency', 'USD')}\n"
    )
    return message

# ------------------------------
# Обработка входящих постбеков от ПП
# ------------------------------
@app.post("/postback")
async def postback_handler(request: Request):
    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"Ошибка при разборе JSON постбека: {e}")
        return {"error": "Некорректный JSON"}, 400

    logger.debug(f"Получен постбек: {data}")

    # Извлекаем необходимые поля
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
        "🔔 *Новая конверсия!*\n\n"
        f"📌 Оффер: {offer_id}\n"
        f"🛠 Подход: {sub_id2}\n"
        f"📊 Тип конверсии: {goal}\n"
        f"💰 Выплата: {revenue} {currency}\n"
        f"⚙️ Статус конверсии: {status}\n"
        f"🎯 Кампания: {sub_id4}\n"
        f"🎯 Адсет: {sub_id5}\n"
        f"⏰ Время конверсии: {conversion_date}"
    )

    try:
        await application.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown")
        logger.debug("Постбек успешно отправлен в Telegram")
    except Exception as e:
        logger.error(f"Ошибка отправки постбека в Telegram: {e}")
        return {"error": "Не удалось отправить сообщение"}, 500

    return {"status": "ok"}

# ------------------------------
# Эндпоинт для получения готовых ссылок с макросами
# ------------------------------
@app.get("/postback_links")
async def postback_links():
    link1 = ("https://postapi-x4hf.onrender.com?"
             "offer_id={offer_id}&sub_id2={sub_id2}&goal={goal}&"
             "revenue={revenue}&currency={currency}&status={status}&"
             "sub_id4={sub_id4}&sub_id5={sub_id5}&conversion_date={conversion_date}")
    link2 = ("https://apiposts-production-1dea.up.railway.app?"
             "offer_id={offer_id}&sub_id2={sub_id2}&goal={goal}&"
             "revenue={revenue}&currency={currency}&status={status}&"
             "sub_id4={sub_id4}&sub_id5={sub_id5}&conversion_date={conversion_date}")
    return {"link1": link1, "link2": link2}

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
# FastAPI сервер для обработки вебхуков (Telegram и постбеки)
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

    # Предполагаем, что если в JSON есть поле "update_id" – это запрос от Telegram,
    # иначе, если, например, присутствует "offer_id", это постбек от ПП.
    if "update_id" in data:
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
    else:
        # Если это не Telegram-обновление, то пробуем обработать как постбек.
        return await postback_handler(request)

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

    headers = {
        "API-KEY": API_KEY,
        "Content-Type": "application/json",
        "User-Agent": "TelegramBot/1.0 (compatible; Alanbase API integration)"
    }

    now = datetime.now()
    
    if text == "Получить статистику":
        period_keyboard = [["За час", "За день"], ["За прошлую неделю"], ["Назад"]]
        reply_markup = ReplyKeyboardMarkup(period_keyboard, resize_keyboard=True, one_time_keyboard=True)
        logger.debug("Отправка клавиатуры для выбора периода статистики")
        await update.message.reply_text("Выберите период статистики:", reply_markup=reply_markup)
    
    elif text in ["За час", "За день", "За прошлую неделю"]:
        period_label = text
        if text == "За час":
            date_from = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
            date_to = now.strftime("%Y-%m-%d %H:%M:%S")
            group_by = "hour"
        elif text == "За день":
            selected_date = now.strftime("%Y-%m-%d 00:00:00")
            date_from = selected_date
            date_to = selected_date
            group_by = "day"
        elif text == "За прошлую неделю":
            weekday = now.weekday()
            last_monday = now - timedelta(days=weekday + 7)
            date_from = last_monday.replace(hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S")
            last_sunday = last_monday + timedelta(days=6)
            date_to = last_sunday.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%d %H:%M:%S")
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
        selected_date = now.strftime("%Y-%m-%d 00:00:00")
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
        date_from = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        date_to = now.strftime("%Y-%m-%d %H:%M:%S")
        params = {
            "timezone": "Europe/Moscow",
            "date_from": date_from,
            "date_to": date_to,
            "currency_code": "USD"
        }
        logger.debug(f"Формирование запроса к {BASE_API_URL}/partner/statistic/conversions с параметрами: {params} и заголовками: {headers}")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{BASE_API_URL}/partner/statistic/conversions", headers=headers, params=params)
            logger.debug(f"Получен ответ API: {response.status_code} - {response.text}")
        except httpx.RequestError as exc:
            logger.error(f"Ошибка запроса к API: {exc}")
            await update.message.reply_text(f"⚠️ Ошибка запроса: {exc}")
            return
        
        if response.status_code == 200:
            try:
                data = response.json()
                message = format_conversion(data)
            except Exception as e:
                logger.error(f"Ошибка обработки JSON: {e}")
                message = "⚠️ Не удалось обработать ответ API."
        else:
            message = f"⚠️ Ошибка API {response.status_code}: {response.text}"
        
        await update.message.reply_text(message, parse_mode="Markdown")
    
    elif text == "🔍 Детальная статистика":
        selected_date = now.strftime("%Y-%m-%d 00:00:00")
        params = {
            "group_by": "offer",
            "timezone": "Europe/Moscow",
            "date_from": selected_date,
            "date_to": selected_date,
            "currency_code": "USD"
        }
        logger.debug(f"Формирование запроса для детальной статистики с параметрами: {params}")
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
                message = format_statistics(data, "Детальная статистика")
            except Exception as e:
                logger.error(f"Ошибка обработки JSON: {e}")
                message = "⚠️ Не удалось обработать ответ API."
        else:
            message = f"⚠️ Ошибка API {response.status_code}: {response.text}"
        await update.message.reply_text(message, parse_mode="Markdown")
    
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
                message = format_offers(data)
            except Exception as e:
                logger.error(f"Ошибка обработки JSON: {e}")
                message = "⚠️ Не удалось обработать ответ API."
        else:
            message = f"⚠️ Ошибка API {response.status_code}: {response.text}"
        await update.message.reply_text(message, parse_mode="Markdown")
    
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

# Регистрация обработчиков команд и сообщений Telegram
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
