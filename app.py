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
logger.debug(f"Конфигурация: PP_API_KEY = {API_KEY[:4]+'****' if API_KEY != 'ВАШ_API_КЛЮЧ' else API_KEY}, TELEGRAM_TOKEN = {TELEGRAM_TOKEN[:4]+'****' if TELEGRAM_TOKEN != 'ВАШ_ТОКЕН' else TELEGRAM_TOKEN}, TELEGRAM_CHAT_ID = {TELEGRAM_CHAT_ID}")

# ------------------------------
# Создание экземпляра FastAPI
# ------------------------------
app = FastAPI()

def get_main_menu():
    # Главное меню всегда содержит только одну кнопку "Получить статистику"
    return ReplyKeyboardMarkup(
        [[KeyboardButton(text="Получить статистику")]],
        resize_keyboard=True,
        one_time_keyboard=False
    )

def get_statistics_menu():
    # Подменю для статистики: "За час", "За сегодня", "За прошлую неделю", "За период", "За месяц", "Назад"
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(text="За час"), KeyboardButton(text="За сегодня")],
            [KeyboardButton(text="За прошлую неделю"), KeyboardButton(text="За период")],
            [KeyboardButton(text="За месяц")],
            [KeyboardButton(text="Назад")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

# ------------------------------
# Функция форматирования статистики согласно API (HTML формат)
# ------------------------------
async def format_statistics(response_json, period_label: str) -> str:
    data = response_json.get("data", [])
    if not data:
        return "⚠️ <i>Статистика не найдена.</i>"
    stat = data[0]
    group_fields = stat.get("group_fields", [])
    date_info = group_fields[0].get("label") if group_fields else "Не указано"
    clicks = stat.get("click_count", "N/A")
    unique_clicks = stat.get("click_unique_count", "N/A")
    conversions = stat.get("conversions", {})
    confirmed = conversions.get("confirmed", {})

    message = (
        f"<b>📊 Статистика ({period_label})</b>\n\n"
        f"<b>Дата:</b> <i>{date_info}</i>\n\n"
        f"<b>Клики:</b>\n"
        f"• <b>Всего:</b> <i>{clicks}</i>\n"
        f"• <b>Уникальные:</b> <i>{unique_clicks}</i>\n\n"
        f"<b>Конверсии:</b>\n"
        f"<b>✅ Подтвержденные:</b> <i>{confirmed.get('count', 'N/A')}</i>\n"
        f"<b>💰 Доход:</b> <i>{confirmed.get('payout', 'N/A')} USD</i>\n"
    )
    return message

# ------------------------------
# Функция форматирования офферов (HTML формат) – не используется, т.к. кнопка удалена
# ------------------------------
async def format_offers(response_json) -> str:
    offers = response_json.get("data", [])
    if not offers:
        return "⚠️ <i>Офферы не найдены.</i>"
    message = "<b>📈 Топ офферы:</b>\n\n"
    for offer in offers:
        message += f"• <b>ID:</b> {offer.get('id')} \\| <b>Название:</b> {offer.get('name')}\n"
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
# Обработка постбеков от ПП (HTML формат)
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
    main_keyboard = get_main_menu()
    logger.debug("Отправка основного меню")
    text = "Привет! Выберите команду:"
    await update.message.reply_text(text, reply_markup=main_keyboard, parse_mode="HTML")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    # Удаляем входящее сообщение, чтобы диалог оставался чистым
    try:
        await update.message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение: {e}")

    text = update.message.text.strip()
    logger.debug(f"Получено сообщение: {text}")

    headers = {
        "API-KEY": API_KEY,
        "Content-Type": "application/json",
        "User-Agent": "TelegramBot/1.0 (compatible; Alanbase API integration)"
    }
    now = datetime.now()  # Можно добавить ZoneInfo("Europe/Moscow"), если требуется

    # Главное меню для статистики
    if text == "Получить статистику":
        reply_markup = get_statistics_menu()
        logger.debug("Отправка подменю для выбора периода статистики")
        await update.message.reply_text("Выберите период статистики:", reply_markup=reply_markup, parse_mode="HTML")
        return

    # Обработка ввода диапазона дат (команда "За период")
    if context.user_data.get("awaiting_period"):
        parts = text.split(",")
        if len(parts) != 2:
            await update.message.reply_text("❗ Неверный формат диапазона. Используйте: YYYY-MM-DD,YYYY-MM-DD", parse_mode="HTML")
            return
        try:
            start_date = datetime.strptime(parts[0].strip(), "%Y-%m-%d").date()
            end_date = datetime.strptime(parts[1].strip(), "%Y-%m-%d").date()
        except ValueError:
            await update.message.reply_text("❗ Неверный формат даты. Используйте формат YYYY-MM-DD.", parse_mode="HTML")
            return
        if start_date > end_date:
            await update.message.reply_text("❗ Начальная дата должна быть раньше конечной.", parse_mode="HTML")
            return
        total_clicks = total_unique = total_confirmed = 0
        total_income = 0.0
        days_count = 0
        current_date = start_date
        while current_date <= end_date:
            d_str = current_date.strftime("%Y-%m-%d")
            date_from = f"{d_str} 00:00"
            date_to = date_from  # Для группировки по дню
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
                await update.message.reply_text(f"⚠️ Ошибка запроса: {e}", parse_mode="HTML")
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
            await update.message.reply_text("⚠️ Статистика не найдена за указанный период.", parse_mode="HTML")
            context.user_data["awaiting_period"] = False
            return
        period_label = f"{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}"
        message = (
            f"<b>📊 Статистика ({period_label})</b>\n\n"
            f"<b>Клики:</b>\n"
            f"• <b>Всего:</b> <i>{total_clicks}</i>\n"
            f"• <b>Уникальные:</b> <i>{total_unique}</i>\n\n"
            f"<b>Конверсии (подтвержденные):</b> <i>{total_confirmed}</i>\n"
            f"<b>Доход:</b> <i>{total_income:.2f} USD</i>"
        )
        await update.message.reply_text(message, parse_mode="HTML", reply_markup=get_main_menu())
        context.user_data["awaiting_period"] = False
        return

    # Основные варианты выбора периода
    if text == "За час":
        period_label = "За час"
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        date_from = current_hour.strftime("%Y-%m-%d %H:%M")
        date_to = date_from  # Для группировки по часу
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
        await update.message.reply_text(message, parse_mode="HTML", reply_markup=get_main_menu())

    elif text == "За сегодня":
        period_label = "За сегодня"
        selected_date = now.strftime("%Y-%m-%d")
        date_from = f"{selected_date} 00:00"
        date_to = f"{selected_date} 00:00"  # Для группировки по дню должны совпадать
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
        await update.message.reply_text(message, parse_mode="HTML", reply_markup=get_main_menu())

    elif text == "За прошлую неделю":
        # Агрегируем статистику за прошлую неделю (с понедельника по воскресенье)
        weekday = now.weekday()
        last_monday = (now - timedelta(days=weekday + 7)).date()
        last_sunday = last_monday + timedelta(days=6)
        period_label = f"За {last_monday.strftime('%Y-%m-%d')} - {last_sunday.strftime('%Y-%m-%d')}"
        total_clicks = total_unique = total_confirmed = 0
        total_income = 0.0
        current_date = last_monday
        while current_date <= last_sunday:
            d_str = current_date.strftime("%Y-%m-%d")
            date_from = f"{d_str} 00:00"
            date_to = date_from  # Для группировки по дню
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
                await update.message.reply_text(f"⚠️ Ошибка запроса: {e}", parse_mode="HTML")
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
            current_date += timedelta(days=1)
        if total_clicks == 0 and total_unique == 0 and total_confirmed == 0:
            message = "⚠️ Статистика не найдена за указанный период."
        else:
            message = (
                f"<b>📊 Статистика ({period_label})</b>\n\n"
                f"<b>Клики:</b>\n"
                f"• <b>Всего:</b> <i>{total_clicks}</i>\n"
                f"• <b>Уникальные:</b> <i>{total_unique}</i>\n\n"
                f"<b>Конверсии (подтвержденные):</b> <i>{total_confirmed}</i>\n"
                f"<b>Доход:</b> <i>{total_income:.2f} USD</i>"
            )
        await update.message.reply_text(message, parse_mode="HTML", reply_markup=get_main_menu())
    
    elif text == "За период":
        await update.message.reply_text("🗓 Введите диапазон дат в формате YYYY-MM-DD,YYYY-MM-DD:", parse_mode="HTML")
        context.user_data["awaiting_period"] = True
    
    elif text == "За месяц":
        # Определяем первый и последний день текущего месяца
        first_day = now.replace(day=1).date()
        if now.month == 12:
            next_month_first = now.replace(year=now.year+1, month=1, day=1).date()
        else:
            next_month_first = now.replace(month=now.month+1, day=1).date()
        last_day = next_month_first - timedelta(days=1)
        period_label = f"За {first_day.strftime('%Y-%m-%d')} - {last_day.strftime('%Y-%m-%d')}"
        total_clicks = total_unique = total_confirmed = 0
        total_income = 0.0
        current_date = first_day
        end_date = last_day
        while current_date <= end_date:
            d_str = current_date.strftime("%Y-%m-%d")
            date_from = f"{d_str} 00:00"
            date_to = date_from  # Для группировки по дню
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
                await update.message.reply_text(f"⚠️ Ошибка запроса: {e}", parse_mode="HTML")
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
            current_date += timedelta(days=1)
        if total_clicks == 0 and total_unique == 0 and total_confirmed == 0:
            message = "⚠️ Статистика не найдена за указанный период."
        else:
            message = (
                f"<b>📊 Статистика ({period_label})</b>\n\n"
                f"<b>Клики:</b>\n"
                f"• <b>Всего:</b> <i>{total_clicks}</i>\n"
                f"• <b>Уникальные:</b> <i>{total_unique}</i>\n\n"
                f"<b>Конверсии (подтвержденные):</b> <i>{total_confirmed}</i>\n"
                f"<b>Доход:</b> <i>{total_income:.2f} USD</i>"
            )
        await update.message.reply_text(message, parse_mode="HTML", reply_markup=get_main_menu())
    
    elif text == "Назад":
        await update.message.reply_text("Возврат в главное меню:", reply_markup=get_main_menu(), parse_mode="HTML")
    
    else:
        await update.message.reply_text("Неизвестная команда. Попробуйте снова.", parse_mode="HTML", reply_markup=get_main_menu())

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
