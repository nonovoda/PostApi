import os
import logging
import asyncio
from datetime import datetime, timedelta
import httpx
from fastapi import FastAPI, Request
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

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

# ------------------------------
# Меню бота (Reply-кнопки)
# ------------------------------
def get_main_menu():
    # Добавили кнопку "ЛК ПП", и "📊 Получить статистику"
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(text="📊 Получить статистику"), KeyboardButton(text="ЛК ПП")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

def get_statistics_menu():
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
# Функция форматирования общей статистики (HTML)
# ------------------------------
async def format_statistics(response_json, period_label: str) -> str:
    data = response_json.get("data", [])
    if not data:
        return f"⚠️ <i>Статистика не найдена ({period_label}).</i>"
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
        f"✅ <b>Подтвержденные:</b> <i>{confirmed.get('count', 'N/A')}</i>\n"
        f"💰 <b>Доход:</b> <i>{confirmed.get('payout', 'N/A')} USD</i>\n"
    )
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
# Унифицированная функция обработки постбеков (GET/POST)
# ------------------------------
async def process_postback_data(data: dict):
    logger.debug(f"Обработка данных конверсии (postback): {data}")
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
        logger.debug("Данные конверсии успешно отправлены в Telegram (postback).")
    except Exception as e:
        logger.error(f"Ошибка отправки данных конверсии в Telegram: {e}")
        return {"error": "Не удалось отправить сообщение в Telegram"}, 500

    return {"status": "ok"}

# ------------------------------
# Унифицированный эндпоинт /webhook (GET, POST)
# ------------------------------
@app.api_route("/webhook", methods=["GET", "POST"])
async def webhook_handler(request: Request):
    logger.debug("Получен запрос на /webhook")

    # Если это GET -> считываем query_params (postback)
    if request.method == "GET":
        data = dict(request.query_params)
        logger.debug(f"Данные из GET-параметров: {data}")
        return await process_postback_data(data)

    # Если это POST -> либо Telegram update, либо postback
    try:
        data = await request.json()
        logger.debug(f"Данные из тела POST: {data}")
    except Exception as e:
        logger.error(f"Ошибка при разборе JSON: {e}")
        return {"error": "Некорректный JSON"}, 400

    # Проверяем, пришли ли данные от Telegram (update_id)
    if "update_id" in data:
        update = Update.de_json(data, telegram_app.bot)
        if not telegram_app.running:
            logger.warning("Telegram Application не запущено, выполняется инициализация...")
            await init_telegram_app()
        try:
            await telegram_app.process_update(update)
            return {"status": "ok"}
        except Exception as e:
            logger.error(f"Ошибка обработки Telegram-обновления: {e}")
            return {"error": "Ошибка сервера"}, 500
    else:
        # Иначе это postback
        return await process_postback_data(data)

# ------------------------------
# /start
# ------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(1)
    last_msg_id = context.user_data.get("last_bot_message_id")
    if last_msg_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_msg_id)
        except Exception as e:
            logger.debug(f"Не удалось удалить предыдущее сообщение бота: {e}")

    main_keyboard = get_main_menu()
    text = "Привет! Выберите команду:"
    sent_msg = await update.message.reply_text(text, reply_markup=main_keyboard, parse_mode="HTML")
    context.user_data["last_bot_message_id"] = sent_msg.message_id

# ------------------------------
# Обработка обычных текстовых кнопок
# ------------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    # Удаляем сообщение пользователя (как в старой логике)
    await asyncio.sleep(1)
    try:
        await update.message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение пользователя: {e}")

    # Удаляем предыдущее сообщение бота (меню/статистику), чтобы не засорять чат
    await asyncio.sleep(1)
    last_msg_id = context.user_data.get("last_bot_message_id")
    if last_msg_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_msg_id)
        except Exception as e:
            logger.debug(f"Не удалось удалить предыдущее сообщение бота: {e}")

    text = update.message.text.strip()
    logger.debug(f"Получено сообщение: {text}")

    # Кнопка "ЛК ПП"
    if text == "ЛК ПП":
        link_text = "Ваш личный кабинет партнёра: https://cabinet.4rabetpartner.com/statistics"
        sent_msg = await update.message.reply_text(link_text, parse_mode="HTML", reply_markup=get_main_menu())
        context.user_data["last_bot_message_id"] = sent_msg.message_id
        return

    # Кнопка "Получить статистику"
    if text == "📊 Получить статистику":
        reply_markup = get_statistics_menu()
        sent_msg = await update.message.reply_text("Выберите период статистики:", reply_markup=reply_markup, parse_mode="HTML")
        context.user_data["last_bot_message_id"] = sent_msg.message_id
        return

    # Кнопка "Назад"
    if text == "↩️ Назад":
        reply_markup = get_main_menu()
        sent_msg = await update.message.reply_text("Возврат в главное меню:", reply_markup=reply_markup, parse_mode="HTML")
        context.user_data["last_bot_message_id"] = sent_msg.message_id
        return

    # -----------  "За сегодня" -----------
    if text == "📅 За сегодня":
        period_label = "За сегодня"
        selected_date = datetime.now().strftime("%Y-%m-%d")
        date_from = f"{selected_date} 00:00"
        date_to = f"{selected_date} 00:00"

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{BASE_API_URL}/partner/statistic/common",
                    headers={"API-KEY": API_KEY, "Content-Type": "application/json"},
                    params={
                        "group_by": "day",
                        "timezone": "Europe/Moscow",
                        "date_from": date_from,
                        "date_to": date_to,
                        "currency_code": "USD"
                    }
                )
            if response.status_code == 200:
                data = response.json()
                message = await format_statistics(data, period_label)
            else:
                message = f"⚠️ Ошибка API {response.status_code}: {response.text}"
        except Exception as e:
            message = f"⚠️ Ошибка запроса: {e}"

        # [NEW] Добавляем inline-кнопку "Детализация", передаём date_from/date_to
        inline_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "Детализация",
                    callback_data=f"details|{date_from}|{date_to}"
                )
            ]
        ])

        sent_msg = await update.message.reply_text(
            message,
            parse_mode="HTML",
            reply_markup=inline_kb
        )
        context.user_data["last_bot_message_id"] = sent_msg.message_id
        return

    # ----------- "За период" -----------
    if text == "🗓 За период":
        await update.message.reply_text("🗓 Введите диапазон дат в формате YYYY-MM-DD,YYYY-MM-DD:", parse_mode="HTML")
        context.user_data["awaiting_period"] = True
        return

    # ----------- "За месяц" -----------
    if text == "📆 За месяц":
        now = datetime.now()
        end_date = now.date()
        start_date = end_date - timedelta(days=30)
        period_label = f"За {start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}"

        total_clicks = total_unique = total_confirmed = 0
        total_income = 0.0
        days_count = 0
        current_date = start_date

        while current_date <= end_date:
            d_str = current_date.strftime("%Y-%m-%d")
            dt_from = f"{d_str} 00:00"
            dt_to = dt_from
            params = {
                "group_by": "day",
                "timezone": "Europe/Moscow",
                "date_from": dt_from,
                "date_to": dt_to,
                "currency_code": "USD"
            }
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.get(
                        f"{BASE_API_URL}/partner/statistic/common",
                        headers={"API-KEY": API_KEY, "Content-Type": "application/json"},
                        params=params
                    )
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
                    total_income += float(conv.get("confirmed", {}).get("payout", 0) or 0)
                    days_count += 1
            current_date += timedelta(days=1)

        if days_count == 0:
            message = "⚠️ Статистика не найдена за указанный период."
        else:
            message = (
                f"<b>📊 Статистика ({period_label})</b>\n\n"
                f"<b>Клики:</b>\n"
                f"• <b>Всего:</b> <i>{total_clicks}</i>\n"
                f"• <b>Уникальные:</b> <i>{total_unique}</i>\n\n"
                f"<b>Конверсии:</b>\n"
                f"✅ <b>Подтвержденные:</b> <i>{total_confirmed}</i>\n"
                f"💰 <b>Доход:</b> <i>{total_income:.2f} USD</i>"
            )

        # [NEW] Для удобства тоже прикрепим инлайн-кнопку «Детализация» за весь период
        # но т.к. у нас "За месяц" делается покадрово по дням, передадим full date_from/date_to
        # например, midnight start_date и midnight end_date
        date_from = f"{start_date.strftime('%Y-%m-%d')} 00:00"
        date_to = f"{end_date.strftime('%Y-%m-%d')} 23:59"
        inline_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "Детализация",
                    callback_data=f"details|{date_from}|{date_to}"
                )
            ]
        ])

        sent_msg = await update.message.reply_text(
            message,
            parse_mode="HTML",
            reply_markup=inline_kb
        )
        context.user_data["last_bot_message_id"] = sent_msg.message_id
        return

    # ----------- Если пользователь вводит даты (за период) -----------
    if context.user_data.get("awaiting_period"):
        parts = text.split(",")
        if len(parts) != 2:
            sent_msg = await update.message.reply_text("❗ Неверный формат диапазона. Используйте: YYYY-MM-DD,YYYY-MM-DD", parse_mode="HTML")
            context.user_data["last_bot_message_id"] = sent_msg.message_id
            return
        try:
            start_date = datetime.strptime(parts[0].strip(), "%Y-%m-%d").date()
            end_date = datetime.strptime(parts[1].strip(), "%Y-%m-%d").date()
        except ValueError:
            sent_msg = await update.message.reply_text("❗ Неверный формат даты. Используйте формат YYYY-MM-DD.", parse_mode="HTML")
            context.user_data["last_bot_message_id"] = sent_msg.message_id
            return
        if start_date > end_date:
            sent_msg = await update.message.reply_text("❗ Начальная дата должна быть раньше конечной.", parse_mode="HTML")
            context.user_data["last_bot_message_id"] = sent_msg.message_id
            return

        total_clicks = total_unique = total_confirmed = 0
        total_income = 0.0
        days_count = 0
        current_date = start_date

        while current_date <= end_date:
            d_str = current_date.strftime("%Y-%m-%d")
            dt_from = f"{d_str} 00:00"
            dt_to = dt_from
            params = {
                "group_by": "day",
                "timezone": "Europe/Moscow",
                "date_from": dt_from,
                "date_to": dt_to,
                "currency_code": "USD"
            }
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.get(
                        f"{BASE_API_URL}/partner/statistic/common",
                        headers={"API-KEY": API_KEY, "Content-Type": "application/json"},
                        params=params
                    )
            except Exception as e:
                sent_msg = await update.message.reply_text(f"⚠️ Ошибка запроса: {e}", parse_mode="HTML")
                context.user_data["last_bot_message_id"] = sent_msg.message_id
                return

            if response.status_code == 200:
                data = response.json()
                if data.get("data"):
                    stat = data["data"][0]
                    total_clicks += int(stat.get("click_count", 0) or 0)
                    total_unique += int(stat.get("click_unique_count", 0) or 0)
                    conv = stat.get("conversions", {})
                    total_confirmed += int(conv.get("confirmed", {}).get("count", 0) or 0)
                    total_income += float(conv.get("confirmed", {}).get("payout", 0) or 0)
                    days_count += 1
            current_date += timedelta(days=1)

        if days_count == 0:
            sent_msg = await update.message.reply_text(
                "⚠️ Статистика не найдена за указанный период.",
                parse_mode="HTML",
                reply_markup=get_main_menu()
            )
            context.user_data["last_bot_message_id"] = sent_msg.message_id
            context.user_data["awaiting_period"] = False
            return

        period_label = f"{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}"
        message = (
            f"<b>📊 Статистика ({period_label})</b>\n\n"
            f"<b>Клики:</b>\n"
            f"• <b>Всего:</b> <i>{total_clicks}</i>\n"
            f"• <b>Уникальные:</b> <i>{total_unique}</i>\n\n"
            f"<b>Конверсии:</b>\n"
            f"✅ <b>Подтвержденные:</b> <i>{total_confirmed}</i>\n"
            f"💰 <b>Доход:</b> <i>{total_income:.2f} USD</i>"
        )

        # [NEW] Inline-кнопка "Детализация" за этот период
        date_from = f"{start_date.strftime('%Y-%m-%d')} 00:00"
        date_to = f"{end_date.strftime('%Y-%m-%d')} 23:59"
        inline_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "Детализация",
                    callback_data=f"details|{date_from}|{date_to}"
                )
            ]
        ])

        sent_msg = await update.message.reply_text(message, parse_mode="HTML", reply_markup=inline_kb)
        context.user_data["last_bot_message_id"] = sent_msg.message_id
        context.user_data["awaiting_period"] = False
        return

    # Если сообщение не распознано
    sent_msg = await update.message.reply_text("Неизвестная команда. Попробуйте снова.", parse_mode="HTML", reply_markup=get_main_menu())
    context.user_data["last_bot_message_id"] = sent_msg.message_id

# ------------------------------
# [NEW] CallbackQueryHandler: инлайн-кнопки "Детализация" / "Назад"
# ------------------------------
async def inline_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # обязательный answer, чтобы Telegram не ждал

    callback_data = query.data  # например: "details|2025-01-01 00:00|2025-01-01 23:59"
    parts = callback_data.split("|")
    action = parts[0]

    if action == "details":
        date_from = parts[1]
        date_to = parts[2]

        # Делаем запрос конверсий по goal_keys REG, FTD, RDS, WD
        params = {
            "timezone": "Europe/Moscow",
            "date_from": date_from,
            "date_to": date_to,
            # Можно добавить "statuses": [1] если нужны только confirmed и т.п.
            "goal_keys": ["REG", "FTD", "RDS", "WD"],
            "per_page": 50
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{BASE_API_URL}/partner/statistic/conversions",
                    headers={"API-KEY": API_KEY, "Content-Type": "application/json"},
                    params=params
                )
            if resp.status_code == 200:
                data = resp.json()
                conv_list = data.get("data", [])
                if not conv_list:
                    details_text = "Детализация: нет конверсий (REG, FTD, RDS, WD) за указанный период."
                else:
                    details_text = "<b>Детализированные конверсии</b>\n\n"
                    # Выведем первые 20
                    for c in conv_list[:20]:
                        cid = c.get("conversion_id")
                        # goal может содержать поле key
                        goal_key = c.get("goal", {}).get("key", "N/A")
                        status = c.get("status")
                        payout = c.get("payout")
                        details_text += (
                            f"ID <b>{cid}</b>, goal=<i>{goal_key}</i>, status=<i>{status}</i>, payout=<i>{payout}</i>\n"
                        )
            else:
                details_text = f"Ошибка API: {resp.status_code} {resp.text}"
        except Exception as e:
            details_text = f"Ошибка запроса: {e}"

        # Кнопка "Назад" (передаём date_from, date_to)
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "Назад",
                    callback_data=f"back|{date_from}|{date_to}"
                )
            ]
        ])
        # Редактируем текущее сообщение
        await query.edit_message_text(text=details_text, parse_mode="HTML", reply_markup=kb)

    elif action == "back":
        # Нужно вернуть прежнюю "общую" статистику
        date_from = parts[1]
        date_to = parts[2]

        # Допустим, у нас group_by="day"
        # Восстанавливаем "общую" статистику
        period_label = "Общий период"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{BASE_API_URL}/partner/statistic/common",
                    headers={"API-KEY": API_KEY, "Content-Type": "application/json"},
                    params={
                        "group_by": "day",
                        "timezone": "Europe/Moscow",
                        "date_from": date_from,
                        "date_to": date_to,
                        "currency_code": "USD"
                    }
                )
            if resp.status_code == 200:
                common_data = resp.json()
                message = await format_statistics(common_data, period_label)
            else:
                message = f"⚠️ Ошибка API {resp.status_code}: {resp.text}"
        except Exception as e:
            message = f"⚠️ Ошибка запроса: {e}"

        # Снова прикрепляем "Детализация" с теми же датами
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "Детализация",
                    callback_data=f"details|{date_from}|{date_to}"
                )
            ]
        ])

        # Редактируем сообщение
        await query.edit_message_text(text=message, parse_mode="HTML", reply_markup=kb)

# ------------------------------
# Регистрация хэндлеров в Telegram
# ------------------------------
telegram_app.add_handler(CommandHandler("start", start_command))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))
telegram_app.add_handler(CallbackQueryHandler(inline_button_handler))  # [NEW]

# ------------------------------
# Основной запуск приложения
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    loop = asyncio.get_event_loop()
    loop.create_task(init_telegram_app())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
