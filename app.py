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
# Новый API URL от поддержки Alanbase:
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
# Функции форматирования
# ------------------------------
async def format_statistics(response_json, period_label: str) -> str:
    data = response_json.get("data", [])
    meta = response_json.get("meta", {})
    # Если meta пришёл как список, преобразуем в пустой словарь
    if isinstance(meta, list):
        meta = {}

    if not data:
        return "⚠️ *Статистика не найдена.*"

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
        f"**📊 Статистика ({period_label})**\n\n"
        f"**Дата:** _{date_info}_\n\n"
        f"**Клики:**\n"
        f"• Всего: *{clicks}*\n"
        f"• Уникальные: *{unique_clicks}*\n\n"
        f"**Конверсии:**\n"
        f"• Подтвержденные: *{confirmed.get('count', 'N/A')}* (💰 *{confirmed.get('payout', 'N/A')} USD*)\n"
        f"• Ожидающие: *{pending.get('count', 'N/A')}* (💰 *{pending.get('payout', 'N/A')} USD*)\n"
        f"• В удержании: *{hold.get('count', 'N/A')}* (💰 *{hold.get('payout', 'N/A')} USD*)\n"
        f"• Отклоненные: *{rejected.get('count', 'N/A')}* (💰 *{rejected.get('payout', 'N/A')} USD*)\n"
        f"• Всего: *{total.get('count', 'N/A')}* (💰 *{total.get('payout', 'N/A')} USD*)\n\n"
        f"**Страница:** *{meta.get('page', 'N/A')}* / **Последняя:** *{meta.get('last_page', 'N/A')}* | **Всего записей:** *{meta.get('total_count', 'N/A')}*"
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
    message += f"\n**Страница:** {meta.get('page', 'N/A')} / **Всего офферов:** {meta.get('total_count', 'N/A')}"
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
# Эндпоинт для обработки постбеков от ПП
# ------------------------------
async def postback_handler(request: Request):
    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"Ошибка при разборе JSON постбека: {e}")
        return {"error": "Некорректный JSON"}, 400

    logger.debug(f"Получен постбек: {data}")
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
        f"**📌 Оффер:** {offer_id}\n"
        f"**🛠 Подход:** {sub_id2}\n"
        f"**📊 Тип конверсии:** {goal}\n"
        f"**💰 Выплата:** {revenue} {currency}\n"
        f"**⚙️ Статус конверсии:** {status}\n"
        f"**🎯 Кампания:** {sub_id4}\n"
        f"**🎯 Адсет:** {sub_id5}\n"
        f"**⏰ Время конверсии:** {conversion_date}"
    )

    try:
        # Экранируем markdown-сущности, чтобы избежать ошибок парсинга
        escaped_message = escape_markdown(message, version=2)
        await telegram_app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=escaped_message, parse_mode="MarkdownV2")
        logger.debug("Постбек успешно отправлен в Telegram")
    except Exception as e:
        logger.error(f"Ошибка отправки постбека в Telegram: {e}")
        return {"error": "Не удалось отправить сообщение"}, 500

    return {"status": "ok"}

# ------------------------------
# Единый эндпоинт для обработки входящих запросов (Telegram и постбеки)
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
# Обработчики команд Telegram (асинхронные)
# ------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    main_keyboard = [
        [KeyboardButton(text="Получить статистику")],
        [KeyboardButton(text="📈 Топ офферы")],
        [KeyboardButton(text="🔄 Обновить данные")],
        [KeyboardButton(text="Тестовый запрос")]
    ]
    reply_markup = ReplyKeyboardMarkup(main_keyboard, resize_keyboard=True, one_time_keyboard=False)
    logger.debug("Отправка основного меню")
    text = "Привет! Выберите команду:"
    # Экранируем текст перед отправкой
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

    if text == "Тестовый запрос":
        # Пустые параметры тестового запроса
        params = {
            "timezone": "",
            "date_from": "",
            "date_to": "",
            "offer_ids": "",
            "country_codes": "",
            "sub1": "",
            "sub2": "",
            "sub3": "",
            "sub4": "",
            "sub5": "",
            "sub6": "",
            "sub7": "",
            "sub8": "",
            "sub9": "",
            "sub10": "",
            "tags": "",
            "currency_code": ""
        }
        full_url = str(httpx.URL(f"{BASE_API_URL}/partner/statistic/common").copy_merge_params(params))
        logger.debug(f"Полный URL тестового запроса: {full_url}")
        logger.debug(f"Отправка тестового запроса к {BASE_API_URL}/partner/statistic/common с заголовками: {headers}")
        start_time = datetime.now()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{BASE_API_URL}/partner/statistic/common", headers=headers, params=params)
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.debug(f"Тестовый запрос выполнен за {elapsed:.2f} сек: {response.status_code} - {response.text}")
        except httpx.RequestError as exc:
            logger.error(f"Ошибка тестового запроса к API: {exc}")
            await update.message.reply_text(f"⚠️ Ошибка тестового запроса: {exc}")
            return

        if response.status_code == 200:
            try:
                data = response.json()
                message = f"✅ Тестовый запрос выполнен успешно:\n```\n{data}\n```"
                escaped_message = escape_markdown(message, version=2)
                await update.message.reply_text(escaped_message, parse_mode="MarkdownV2")
            except Exception as e:
                logger.error(f"Ошибка обработки JSON в тестовом запросе: {e}")
                await update.message.reply_text("⚠️ Не удалось обработать ответ API тестового запроса.")
        else:
            message = f"⚠️ Тестовый запрос: Ошибка API {response.status_code}: {response.text}"
            await update.message.reply_text(message)
    
    elif text == "Получить статистику":
        period_keyboard = [["За час", "За день"], ["За прошлую неделю"], ["Назад"]]
        reply_markup = ReplyKeyboardMarkup(period_keyboard, resize_keyboard=True, one_time_keyboard=True)
        logger.debug("Отправка подменю для выбора периода статистики")
        await update.message.reply_text("Выберите период статистики:", reply_markup=reply_markup)
    
    elif text in ["За час", "За день", "За прошлую неделю"]:
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
        
        # Экранируем сообщение перед отправкой
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
            [KeyboardButton(text="🔄 Обновить данные")],
            [KeyboardButton(text="Тестовый запрос")]
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
