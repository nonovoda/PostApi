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

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# ------------------------------
# Создание экземпляра FastAPI
# ------------------------------
app = FastAPI()

# ------------------------------
# Главное меню (Reply-кнопки)
# ------------------------------
def get_main_menu():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📊 Получить статистику"), KeyboardButton("ЛК ПП")],
            [KeyboardButton("⬅️ Назад")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

# ------------------------------
# Функция форматирования статистики (common)
# ------------------------------
async def format_common_stats(data_json, period_label: str) -> str:
    arr = data_json.get("data", [])
    if not arr:
        return f"⚠️ Нет статистики ({period_label})."
    st = arr[0]
    gf = st.get("group_fields", [])
    date_info = gf[0].get("label") if gf else "N/A"
    clicks = st.get("click_count", 0)
    unique_clicks = st.get("click_unique_count", 0)
    conf = st.get("conversions", {}).get("confirmed", {})
    count_conf = conf.get("count", 0)
    payout_conf = conf.get("payout", 0)

    msg = (
        f"<b>📊 Статистика ({period_label})</b>\n\n"
        f"🗓 Даты: <i>{date_info}</i>\n\n"
        f"👀 Клики: <b>{clicks}</b> (уник: {unique_clicks})\n\n"
        f"✅ Подтвержденные: <b>{count_conf}</b>\n"
        f"💰 Доход: <b>{payout_conf} USD</b>\n"
    )
    return msg

# ------------------------------
# Запрос /common
# ------------------------------
async def get_common_data(date_from: str, date_to: str):
    """
    Делает запрос /partner/statistic/common, возвращает (ok, data | error_str).
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_API_URL}/partner/statistic/common",
                headers={"API-KEY": API_KEY},
                params={
                    "group_by": "day",
                    "timezone": "Europe/Moscow",
                    "date_from": date_from,
                    "date_to": date_to,
                    "currency_code": "USD"
                }
            )
        if resp.status_code == 200:
            return True, resp.json()
        else:
            return False, f"⚠️ Ошибка /common: {resp.status_code}, {resp.text}"
    except Exception as e:
        return False, f"⚠️ Ошибка запроса: {e}"

# ------------------------------
# Суммарная детализация по 4 целям
# ------------------------------
async def get_goals_detail(date_from: str, date_to: str):
    """
    Суммируем конверсии/payout по goal_keys[]= registration, ftd, bet, rdeposit
    """
    base_params = [
        ("timezone", "Europe/Moscow"),
        ("date_from", date_from),
        ("date_to", date_to),
        ("per_page", "500"),
    ]
    for g in ["registration", "ftd", "bet", "rdeposit"]:
        base_params.append(("goal_keys[]", g))

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_API_URL}/partner/statistic/conversions",
                headers={"API-KEY": API_KEY},
                params=base_params
            )
        if resp.status_code != 200:
            return f"⚠️ Ошибка детализации: {resp.status_code}, {resp.text}"

        data = resp.json().get("data", [])
        if not data:
            return "❗ Нет конверсий по этим целям."

        # Группируем
        goals_map = {
            "registration": {"count": 0, "payout": 0},
            "ftd": {"count": 0, "payout": 0},
            "bet": {"count": 0, "payout": 0},
            "rdeposit": {"count": 0, "payout": 0},
        }
        for c in data:
            gk = c.get("goal", {}).get("key")
            if gk in goals_map:
                goals_map[gk]["count"] += 1
                goals_map[gk]["payout"] += float(c.get("payout", 0))

        txt = "<b>Общая детализация</b>\n\n"
        emoji = {
            "registration": "🆕",
            "ftd": "💵",
            "bet": "🎰",
            "rdeposit": "🔄",
        }
        for k, val in goals_map.items():
            txt += (
                f"{emoji.get(k,'')} <b>{k}</b>: {val['count']} шт., payout <i>{val['payout']}</i>\n"
            )
        return txt
    except Exception as e:
        return f"⚠️ Ошибка при загрузке детализации: {e}"

# ------------------------------
# Обработка POSTBACK (конверсии)
# ------------------------------
async def process_postback_data(data: dict):
    """
    Восстанавливаем формат «новая конверсия»:
    """
    logger.debug(f"Postback data: {data}")
    offer_id = data.get("offer_id", "N/A")
    sub_id2 = data.get("sub_id2", "N/A")
    goal = data.get("goal", "N/A")
    revenue = data.get("revenue", "N/A")
    currency = data.get("currency", "USD")
    status = data.get("status", "N/A")
    sub_id4 = data.get("sub_id4", "N/A")
    sub_id5 = data.get("sub_id5", "N/A")
    conversion_date = data.get("conversion_date", "N/A")

    msg = (
        "🔔 <b>Новая конверсия!</b>\n\n"
        f"<b>📌 Оффер:</b> <i>{offer_id}</i>\n"
        f"<b>🛠 Подход:</b> <i>{sub_id2}</i>\n"
        f"<b>📊 Тип конверсии:</b> <i>{goal}</i>\n"
        f"<b>💰 Выплата:</b> <i>{revenue} {currency}</i>\n"
        f"<b>⚙️ Статус:</b> <i>{status}</i>\n"
        f"<b>🎯 Кампания:</b> <i>{sub_id4}</i>\n"
        f"<b>🎯 Адсет:</b> <i>{sub_id5}</i>\n"
        f"<b>⏰ Время конверсии:</b> <i>{conversion_date}</i>"
    )

    try:
        await telegram_app.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=msg,
            parse_mode="HTML",
            reply_markup=get_main_menu()
        )
        logger.debug("Сообщение о постбеке отправлено в Telegram.")
    except Exception as e:
        logger.error(f"Ошибка при отправке постбека: {e}")
        return {"error": "Не удалось отправить сообщение"}, 500

    return {"status": "ok"}

# ------------------------------
# Webhook эндпоинт
# ------------------------------
@app.api_route("/webhook", methods=["GET","POST"])
async def webhook_handler(request: Request):
    """
    Унифицированный webhook: либо Telegram update, либо postback (GET/POST).
    """
    if request.method == "GET":
        # postback GET
        data = dict(request.query_params)
        return await process_postback_data(data)

    # Иначе POST
    try:
        data = await request.json()
        if "update_id" in data:
            # Telegram update
            update = Update.de_json(data, telegram_app.bot)
            if not telegram_app.running:
                await init_telegram_app()
            await telegram_app.process_update(update)
            return {"status": "ok"}
        else:
            # postback
            return await process_postback_data(data)
    except:
        return {"status": "ok"}

# ------------------------------
# Инициализация бота
# ------------------------------
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

async def init_telegram_app():
    logger.info("Инициализация Telegram-бота...")
    await telegram_app.initialize()
    await telegram_app.start()
    logger.info("Telegram-бот запущен!")

# ------------------------------
# /start
# ------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(1)
    last_id = context.user_data.get("last_msg_id")
    if last_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_id)
        except:
            pass

    text = "Привет! Выберите команду:"
    mk = get_main_menu()
    sent = await update.message.reply_text(text, parse_mode="HTML", reply_markup=mk)
    context.user_data["last_msg_id"] = sent.message_id

# ------------------------------
# Обработка Reply-кнопок
# ------------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Удаляем сообщение пользователя
    await asyncio.sleep(1)
    try:
        await update.message.delete()
    except:
        pass

    # Удаляем старое сообщение бота
    await asyncio.sleep(1)
    last_id = context.user_data.get("last_msg_id")
    if last_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_id)
        except:
            pass

    text = update.message.text.strip()

    if text == "ЛК ПП":
        link_msg = "Ваш личный кабинет: https://cabinet.4rabetpartner.com/statistics"
        sent = await update.message.reply_text(link_msg, parse_mode="HTML", reply_markup=get_main_menu())
        context.user_data["last_msg_id"] = sent.message_id
        return

    if text == "📊 Получить статистику":
        # Отправляем inline-кнопки
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Сегодня", callback_data="period_today"),
                InlineKeyboardButton("7 дней", callback_data="period_7days"),
                InlineKeyboardButton("За месяц", callback_data="period_month"),
            ],
            [
                InlineKeyboardButton("Свой период", callback_data="period_custom")
            ],
            [
                InlineKeyboardButton("Назад", callback_data="back_mainmenu")
            ]
        ])
        sent = await update.message.reply_text("Выберите период:", parse_mode="HTML", reply_markup=kb)
        context.user_data["last_msg_id"] = sent.message_id
        return

    if text in ["⬅️ Назад"]:
        mk = get_main_menu()
        msg = await update.message.reply_text("Главное меню:", parse_mode="HTML", reply_markup=mk)
        context.user_data["last_msg_id"] = msg.message_id
        return

    # Неизвестная команда
    msg = await update.message.reply_text("Неизвестная команда", parse_mode="HTML", reply_markup=get_main_menu())
    context.user_data["last_msg_id"] = msg.message_id

# ------------------------------
# Обработка inline-кнопок
# ------------------------------
async def inline_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    logger.debug(f"Callback data: {data}")

    # Назад в главное меню
    if data == "back_mainmenu":
        await query.edit_message_text("Главное меню", parse_mode="HTML")
        await query.edit_message_reply_markup(None)
        mk = get_main_menu()
        sent = await query.message.reply_text("Главное меню:", parse_mode="HTML", reply_markup=mk)
        context.user_data["last_msg_id"] = sent.message_id
        return

    # Готовые периоды
    if data == "period_today":
        d_str = datetime.now().strftime("%Y-%m-%d")
        date_from = f"{d_str} 00:00"
        date_to   = f"{d_str} 23:59"
        label     = "Сегодня"
        await show_common_stat(query, context, date_from, date_to, label)
        return

    elif data == "period_7days":
        end_d = datetime.now().date()
        start_d = end_d - timedelta(days=6)
        date_from = f"{start_d} 00:00"
        date_to   = f"{end_d} 23:59"
        label     = "Последние 7 дней"
        await show_common_stat(query, context, date_from, date_to, label)
        return

    elif data == "period_month":
        end_d = datetime.now().date()
        start_d = end_d - timedelta(days=30)
        date_from = f"{start_d} 00:00"
        date_to   = f"{end_d} 23:59"
        label     = "Последние 30 дней"
        await show_common_stat(query, context, date_from, date_to, label)
        return

    elif data == "period_custom":
        # Попросим ввести датy вручную
        txt = (
            "<b>Введите период</b> (YYYY-MM-DD,YYYY-MM-DD)\n"
            "Например: 2025-02-01,2025-02-10\n"
            "Чтобы отменить, напишите \"Назад\""
        )
        await query.edit_message_text(txt, parse_mode="HTML", reply_markup=None)
        # Задаём флаг, что ждём текст
        context.user_data["awaiting_custom_period"] = True
        # Сохраняем, какое сообщение редактировать
        context.user_data["inline_msg_id"] = query.message.message_id
        return

    # Детализация
    if data.startswith("details|"):
        parts = data.split("|")
        date_from = parts[1]
        date_to   = parts[2]
        label     = parts[3]
        detail = await get_goals_detail(date_from, date_to)
        txt_out = f"<b>Детализация ({label})</b>\n\n{detail}"
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Назад", callback_data=f"common_back|{date_from}|{date_to}|{label}")
            ]
        ])
        await query.edit_message_text(txt_out, parse_mode="HTML", reply_markup=kb)
        return

    if data.startswith("common_back|"):
        # Вернёмся к статистике /common
        parts = data.split("|")
        date_from = parts[1]
        date_to   = parts[2]
        label     = parts[3]
        await show_common_stat(query, context, date_from, date_to, label)
        return

    await query.edit_message_text("Неизвестная команда", parse_mode="HTML")

# ------------------------------
# Показ /common + кнопка "Детализация"
# ------------------------------
async def show_common_stat(query, context, date_from: str, date_to: str, label: str):
    ok, data_or_error = await get_common_data(date_from, date_to)
    if not ok:
        text = str(data_or_error)
    else:
        text = await format_common_stats(data_or_error, label)

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Детализация", callback_data=f"details|{date_from}|{date_to}|{label}")
        ],
        [
            InlineKeyboardButton("Назад", callback_data="back_mainmenu")
        ]
    ])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)

# ------------------------------
# Обработка текста (свой период)
# ------------------------------
async def text_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_custom_period"):
        # Если пользователь ввёл "Назад"
        text = update.message.text.strip()
        if text.lower() == "назад":
            context.user_data["awaiting_custom_period"] = False
            # Восстановим меню выбора периода
            inline_msg_id = context.user_data["inline_msg_id"]
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Сегодня", callback_data="period_today"),
                    InlineKeyboardButton("7 дней", callback_data="period_7days"),
                    InlineKeyboardButton("За месяц", callback_data="period_month"),
                ],
                [
                    InlineKeyboardButton("Свой период", callback_data="period_custom")
                ],
                [
                    InlineKeyboardButton("Назад", callback_data="back_mainmenu")
                ]
            ])
            await update.message.delete()
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=inline_msg_id,
                    text="Выберите период:",
                    parse_mode="HTML",
                    reply_markup=kb
                )
            except Exception as e:
                logger.error(f"Ошибка при возврате: {e}")
            return

        # Иначе парсим даты
        parts = text.split(",")
        if len(parts) != 2:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❗ Неверный формат. Введите YYYY-MM-DD,YYYY-MM-DD или 'Назад'"
            )
            return
        try:
            start_d = datetime.strptime(parts[0].strip(), "%Y-%m-%d").date()
            end_d   = datetime.strptime(parts[1].strip(), "%Y-%m-%d").date()
        except:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❗ Ошибка разбора дат. Попробуйте снова или 'Назад'."
            )
            return

        if start_d > end_d:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❗ Начальная дата больше конечной! Попробуйте снова или 'Назад'."
            )
            return

        context.user_data["awaiting_custom_period"] = False
        inline_msg_id = context.user_data["inline_msg_id"]
        await update.message.delete()

        date_from = f"{start_d} 00:00"
        date_to   = f"{end_d} 23:59"
        label     = f"{start_d} - {end_d}"

        # Делаем /common
        ok, data_or_error = await get_common_data(date_from, date_to)
        if not ok:
            text_final = str(data_or_error)
        else:
            text_final = await format_common_stats(data_or_error, label)

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Детализация", callback_data=f"details|{date_from}|{date_to}|{label}")
            ],
            [
                InlineKeyboardButton("Назад", callback_data="back_mainmenu")
            ]
        ])
        try:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=inline_msg_id,
                text=text_final,
                parse_mode="HTML",
                reply_markup=kb
            )
        except Exception as e:
            logger.error(f"Ошибка edit_message_text: {e}")
    else:
        # Не ждём период => возможно это Reply-кнопка
        pass

# ------------------------------
# Регистрация хэндлеров
# ------------------------------
telegram_app.add_handler(CommandHandler("start", start_command))
# Сначала проверяем, не вводит ли пользователь период:
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_input_handler), group=1)
# Если нет - обрабатываем Reply-кнопки:
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler), group=2)
# Инлайн-кнопки:
telegram_app.add_handler(CallbackQueryHandler(inline_button_handler))

# ------------------------------
# Запуск
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    loop = asyncio.get_event_loop()
    loop.create_task(init_telegram_app())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
