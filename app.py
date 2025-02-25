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
# Функция форматирования статистики согласно API
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
    conversions = stat.get("conversions", {})
    confirmed = conversions.get("confirmed", {})
    message = (
        f"**📊 Статистика ({period_label})**\n\n"
        f"**Дата:** _{date_info}_\n\n"
        f"**Клики:**\n"
        f"• **Всего:** _{clicks}_\n"
        f"• **Уникальные:** _{unique_clicks}_\n\n"
        f"**Конверсии:**\n"
        f"• **Подтвержденные:** _{confirmed.get('count', 'N/A')}_ (💰 _{confirmed.get('payout', 'N/A')} USD_)\n"
    )
    return message

# ------------------------------
# Функция форматирования офферов (рабочая версия)
# ------------------------------
async def format_offers(response_json) -> str:
    offers = response_json.get("data", [])
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
# Обработка постбеков от ПП (рабочая версия)
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
        # Перед отправкой не вызываем escape_markdown на всем сообщении – форматирование должно сохраниться.
        await telegram_app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="MarkdownV2")
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
    # В сообщении форматирование уже задано – не экранируем полностью.
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="MarkdownV2")

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
            [KeyboardButton(text="За прошлую неделю"), KeyboardButton(text="За дату")],
            [KeyboardButton(text="За период")],
            [KeyboardButton(text="Назад")]
        ]
        reply_markup = ReplyKeyboardMarkup(period_keyboard, resize_keyboard=True, one_time_keyboard=True)
        logger.debug("Отправка подменю для выбора периода статистики")
        await update.message.reply_text("Выберите период статистики:", reply_markup=reply_markup)
        return

    # Обработка ввода даты (команда "За дату")
    if context.user_data.get("awaiting_date"):
        try:
            date_obj = datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            await update.message.reply_text("❗ Неверный формат даты. Используйте формат YYYY-MM-DD.")
            return
        period_label = f"За {date_obj.strftime('%Y-%m-%d')}"
        date_str = date_obj.strftime("%Y-%m-%d")
        date_from = f"{date_str} 00:00"
        # Для режима "За дату" API требует, чтобы date_to = date_from
        date_to = date_from
        params = {
            "group_by": "day",
            "timezone": "Europe/Moscow",
            "date_from": date_from,
            "date_to": date_to,
            "currency_code": "USD"
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{BASE_API_URL}/partner/statistic/common", headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                message = await format_statistics(data, period_label)
            else:
                message = f"⚠️ Ошибка API {response.status_code}: {response.text}"
        except Exception as e:
            message = f"⚠️ Ошибка запроса: {e}"
        await update.message.reply_text(message, parse_mode="MarkdownV2")
        context.user_data["awaiting_date"] = False
        return

    # Обработка ввода диапазона дат (команда "За период")
    if context.user_data.get("awaiting_period"):
        parts = text.split(",")
        if len(parts) != 2:
            await update.message.reply_text("❗ Неверный формат диапазона. Используйте: YYYY-MM-DD,YYYY-MM-DD")
            return
        try:
            start_date = datetime.strptime(parts[0].strip(), "%Y-%m-%d").date()
            end_date = datetime.strptime(parts[1].strip(), "%Y-%m-%d").date()
        except ValueError:
            await update.message.reply_text("❗ Неверный формат даты. Используйте формат YYYY-MM-DD.")
            return
        if start_date > end_date:
            await update.message.reply_text("❗ Начальная дата должна быть раньше конечной.")
            return
        total_clicks = 0
        total_unique = 0
        total_confirmed = 0
        total_income = 0.0
        days_count = 0
        current_date = start_date
        while current_date <= end_date:
            d_str = current_date.strftime("%Y-%m-%d")
            date_from = f"{d_str} 00:00"
            # Для группировки по дню API требует, чтобы date_to совпадал с date_from
            date_to = date_from
            params = {
                "group_by": "day",
                "timezone": "Europe/Moscow",
                "date_from": date_from,
                "date_to": date_to,
                "currency_code": "USD"
            }
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.get(f"{BASE_API_URL}/partner/statistic/common", headers=headers, params=params)
            except Exception as e:
                await update.message.reply_text(f"⚠️ Ошибка запроса: {e}")
                return
            if response.status_code == 200:
                data = response.json()
                if data.get("data"):
                    stat = data["data"][0]
                    total_clicks += int(stat.get("click_count", 0) or 0)
                    total_unique += int(stat.get("click_unique_count", 0) or 0)
                    conv = stat.get("conversions", {})
                    total_confirmed += int(conv.get("confirmed", {}).get("count", 0) or 0)
                    total_income += float(conv.get("confirmed", {}).get("income", 0) or 0)
                    days_count += 1
            current_date += timedelta(days=1)
        if days_count == 0:
            await update.message.reply_text("⚠️ Статистика не найдена за указанный период.")
            context.user_data["awaiting_period"] = False
            return
        period_label = f"{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}"
        message = (
            f"**📊 Статистика ({period_label})**\n\n"
            f"**Клики:**\n"
            f"• **Всего:** _{total_clicks}_\n"
            f"• **Уникальные:** _{total_unique}_\n\n"
            f"**Конверсии (подтвержденные):** _{total_confirmed}_\n"
            f"**Доход:** _{total_income:.2f} USD_"
        )
        await update.message.reply_text(message, parse_mode="MarkdownV2")
        context.user_data["awaiting_period"] = False
        return

    # Основные варианты выбора периода
    if text == "За час":
        period_label = "За час"
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        date_from = current_hour.strftime("%Y-%m-%d %H:%M")
        # Для группировки по часу API требует, чтобы date_from и date_to совпадали
        date_to = date_from
        params = {
            "group_by": "hour",
            "timezone": "Europe/Moscow",
            "date_from": date_from,
            "date_to": date_to,
            "currency_code": "USD"
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{BASE_API_URL}/partner/statistic/common", headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                message = await format_statistics(data, period_label)
            else:
                message = f"⚠️ Ошибка API {response.status_code}: {response.text}"
        except Exception as e:
            message = f"⚠️ Ошибка запроса: {e}"
        await update.message.reply_text(message, parse_mode="MarkdownV2")
    
    elif text == "За день":
        period_label = "За день"
        selected_date = now.strftime("%Y-%m-%d")
        date_from = f"{selected_date} 00:00"
        # Для группировки по дню API требует, чтобы date_from == date_to
        date_to = date_from
        params = {
            "group_by": "day",
            "timezone": "Europe/Moscow",
            "date_from": date_from,
            "date_to": date_to,
            "currency_code": "USD"
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{BASE_API_URL}/partner/statistic/common", headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                message = await format_statistics(data, period_label)
            else:
                message = f"⚠️ Ошибка API {response.status_code}: {response.text}"
        except Exception as e:
            message = f"⚠️ Ошибка запроса: {e}"
        await update.message.reply_text(message, parse_mode="MarkdownV2")
    
    elif text == "За прошлую неделю":
        period_label = "За прошлую неделю (первый день)"
        # Для соответствия требованию API выбираем первый день прошлой недели
        last_week_start = (now - timedelta(days=now.weekday() + 7)).replace(hour=0, minute=0, second=0, microsecond=0)
        date_from = last_week_start.strftime("%Y-%m-%d %H:%M")
        # Для группировки по дню API требуется, чтобы date_from == date_to
        date_to = date_from
        params = {
            "group_by": "day",
            "timezone": "Europe/Moscow",
            "date_from": date_from,
            "date_to": date_to,
            "currency_code": "USD"
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{BASE_API_URL}/partner/statistic/common", headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                message = await format_statistics(data, period_label)
            else:
                message = f"⚠️ Ошибка API {response.status_code}: {response.text}"
        except Exception as e:
            message = f"⚠️ Ошибка запроса: {e}"
        await update.message.reply_text(message, parse_mode="MarkdownV2")
    
    elif text == "За дату":
        await update.message.reply_text("🗓 Введите дату в формате YYYY-MM-DD:")
        context.user_data["awaiting_date"] = True
    
    elif text == "За период":
        await update.message.reply_text("🗓 Введите диапазон дат в формате YYYY-MM-DD,YYYY-MM-DD:")
        context.user_data["awaiting_period"] = True
    
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
        except Exception as exc:
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
        await update.message.reply_text(message, parse_mode="MarkdownV2")
    
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
