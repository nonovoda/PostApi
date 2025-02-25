import os
import logging
import asyncio
from datetime import datetime, timedelta
import httpx
from fastapi import FastAPI, Request
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (Application, CommandHandler, MessageHandler, filters,
                          ContextTypes, ConversationHandler)

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

def get_main_menu():
    # Главное меню с кнопками: статистика и калькулятор
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(text="📊 Получить статистику")],
            [KeyboardButton(text="🧮 Калькулятор")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

def get_statistics_menu():
    # Подменю статистики с эмодзи
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(text="📅 За сегодня")],
            [KeyboardButton(text="🗓 За период"), KeyboardButton(text="📆 За месяц")],
            [KeyboardButton(text="↩️ Назад")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def get_calculator_menu():
    # Подменю калькулятора с четырьмя функциями
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(text="📈 ROI"), KeyboardButton(text="💹 EPC")],
            [KeyboardButton(text="🛒 СЧ"), KeyboardButton(text="💸 CPA")],
            [KeyboardButton(text="↩️ Назад")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

# ------------------------------
# Функция форматирования статистики (HTML формат)
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
# Обработка постбеков (HTML формат)
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

# ==============================
# КОНВЕРСАЦИИ ДЛЯ РАЗДЕЛА "КАЛЬКУЛЯТОР"
# ==============================

# --- ROI ---
ROI_INVEST, ROI_INCOME = range(2)

async def roi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📈 Введите сумму инвестиций:")
    return ROI_INVEST

async def roi_investment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        investment = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❗ Неверный формат. Введите сумму инвестиций числом:")
        return ROI_INVEST
    context.user_data["investment"] = investment
    await update.message.reply_text("📈 Введите доход:")
    return ROI_INCOME

async def roi_income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        income = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❗ Неверный формат. Введите доход числом:")
        return ROI_INCOME
    investment = context.user_data.get("investment")
    if not investment:
        await update.message.reply_text("❗ Ошибка: не задана сумма инвестиций.")
        return ConversationHandler.END
    roi = ((income - investment) / investment) * 100 if investment != 0 else 0
    await update.message.reply_text(f"📈 ROI: {roi:.2f}%")
    return ConversationHandler.END

async def roi_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📈 ROI-калькулятор отменён.")
    return ConversationHandler.END

roi_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex('^📈 ROI$'), roi_command)],
    states={
        ROI_INVEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, roi_investment)],
        ROI_INCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, roi_income)],
    },
    fallbacks=[CommandHandler("cancel", roi_cancel)]
)

# --- EPC ---
EPC_INCOME, EPC_CLICKS = range(2)

async def epc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💹 Введите доход:")
    return EPC_INCOME

async def epc_income(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        income = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❗ Неверный формат. Введите доход числом:")
        return EPC_INCOME
    context.user_data["income"] = income
    await update.message.reply_text("💹 Введите количество кликов:")
    return EPC_CLICKS

async def epc_clicks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        clicks = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❗ Неверный формат. Введите количество кликов числом:")
        return EPC_CLICKS
    income = context.user_data.get("income")
    if clicks == 0:
        await update.message.reply_text("❗ Количество кликов не может быть нулевым.")
        return ConversationHandler.END
    epc = income / clicks
    await update.message.reply_text(f"💹 EPC: {epc:.2f}")
    return ConversationHandler.END

async def epc_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💹 EPC-калькулятор отменён.")
    return ConversationHandler.END

epc_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex('^💹 EPC$'), epc_command)],
    states={
        EPC_INCOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, epc_income)],
        EPC_CLICKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, epc_clicks)],
    },
    fallbacks=[CommandHandler("cancel", epc_cancel)]
)

# --- Средний чек (СЧ) ---
SC_FIRST, SC_REPEAT, SC_COUNT = range(3)

async def sc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛒 Введите сумму первого депозита:")
    return SC_FIRST

async def sc_first(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        first = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❗ Неверный формат. Введите сумму первого депозита числом:")
        return SC_FIRST
    context.user_data["first"] = first
    await update.message.reply_text("🛒 Введите сумму повторного депозита:")
    return SC_REPEAT

async def sc_repeat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        repeat = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❗ Неверный формат. Введите сумму повторного депозита числом:")
        return SC_REPEAT
    context.user_data["repeat"] = repeat
    await update.message.reply_text("🛒 Введите количество первых депозитов:")
    return SC_COUNT

async def sc_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❗ Неверный формат. Введите количество первых депозитов числом:")
        return SC_COUNT
    first = context.user_data.get("first")
    repeat = context.user_data.get("repeat")
    if count == 0:
        await update.message.reply_text("❗ Количество первых депозитов не может быть нулевым.")
        return ConversationHandler.END
    avg = (first + repeat) / count
    await update.message.reply_text(f"🛒 Средний чек: {avg:.2f}")
    return ConversationHandler.END

async def sc_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛒 Калькулятор среднего чека отменён.")
    return ConversationHandler.END

sc_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex('^🛒 СЧ$'), sc_command)],
    states={
        SC_FIRST: [MessageHandler(filters.TEXT & ~filters.COMMAND, sc_first)],
        SC_REPEAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sc_repeat)],
        SC_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, sc_count)],
    },
    fallbacks=[CommandHandler("cancel", sc_cancel)]
)

# --- CPA ---
CPA_COST, CPA_CONVERSIONS = range(2)

async def cpa_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💸 Введите расходы:")
    return CPA_COST

async def cpa_cost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        cost = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❗ Неверный формат. Введите расходы числом:")
        return CPA_COST
    context.user_data["cost"] = cost
    await update.message.reply_text("💸 Введите количество конверсий:")
    return CPA_CONVERSIONS

async def cpa_conversions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        convs = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❗ Неверный формат. Введите количество конверсий числом:")
        return CPA_CONVERSIONS
    cost = context.user_data.get("cost")
    if convs == 0:
        await update.message.reply_text("❗ Количество конверсий не может быть нулевым.")
        return ConversationHandler.END
    cpa = cost / convs
    await update.message.reply_text(f"💸 CPA: {cpa:.2f}")
    return ConversationHandler.END

async def cpa_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💸 CPA-калькулятор отменён.")
    return ConversationHandler.END

cpa_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex('^💸 CPA$'), cpa_command)],
    states={
        CPA_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, cpa_cost)],
        CPA_CONVERSIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, cpa_conversions)],
    },
    fallbacks=[CommandHandler("cancel", cpa_cancel)]
)

# ==============================
# Обработчики команд Telegram (главное меню и универсальный MessageHandler)
# ==============================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    main_keyboard = get_main_menu()
    logger.debug("Отправка главного меню")
    text = "Привет! Выберите команду:"
    sent_msg = await update.message.reply_text(text, reply_markup=main_keyboard, parse_mode="HTML")
    context.user_data["last_bot_message_id"] = sent_msg.message_id

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    try:
        await update.message.delete()
    except Exception as e:
        logger.debug(f"Не удалось удалить сообщение пользователя: {e}")

    # Удаляем предыдущее сообщение бота, если оно существует
    last_msg_id = context.user_data.get("last_bot_message_id")
    if last_msg_id:
        try:
            await update.message.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_msg_id)
        except Exception as e:
            logger.debug(f"Не удалось удалить предыдущее сообщение бота: {e}")

    text = update.message.text.strip()
    logger.debug(f"Получено сообщение: {text}")

    if text == "📊 Получить статистику":
        reply_markup = get_statistics_menu()
        sent_msg = await update.message.reply_text("Выберите период статистики:", reply_markup=reply_markup, parse_mode="HTML")
        context.user_data["last_bot_message_id"] = sent_msg.message_id
        return
    if text == "🧮 Калькулятор":
        reply_markup = get_calculator_menu()
        sent_msg = await update.message.reply_text("Выберите функцию калькулятора:", reply_markup=reply_markup, parse_mode="HTML")
        context.user_data["last_bot_message_id"] = sent_msg.message_id
        return
    if text == "↩️ Назад":
        reply_markup = get_main_menu()
        sent_msg = await update.message.reply_text("Возврат в главное меню:", reply_markup=reply_markup, parse_mode="HTML")
        context.user_data["last_bot_message_id"] = sent_msg.message_id
        return

    sent_msg = await update.message.reply_text("Неизвестная команда. Попробуйте снова.", parse_mode="HTML", reply_markup=get_main_menu())
    context.user_data["last_bot_message_id"] = sent_msg.message_id

# ==============================
# Регистрация обработчиков Telegram
# ==============================
telegram_app.add_handler(CommandHandler("start", start_command))
telegram_app.add_handler(roi_conv_handler)
telegram_app.add_handler(epc_conv_handler)
telegram_app.add_handler(sc_conv_handler)
telegram_app.add_handler(cpa_conv_handler)
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))

# ------------------------------
# Основной запуск приложения
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    loop = asyncio.get_event_loop()
    loop.create_task(init_telegram_app())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
