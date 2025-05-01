import os
import logging
import asyncio
from datetime import datetime, timedelta
import httpx
import json
import uuid
from fastapi import FastAPI, Request
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

# ------------------------------
# Конфигурация
# ------------------------------
API_KEY = os.getenv("PP_API_KEY", "ВАШ_API_КЛЮЧ")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН")
BASE_API_URL = "https://4rabet.api.alanbase.com/v1"
PORT = int(os.environ.get("PORT", 8000))
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

# ------------------------------
# Система контроля доступа
# ------------------------------
async def check_access(update: Update) -> bool:
    try:
        current = int(update.effective_chat.id)
        allowed = int(TELEGRAM_CHAT_ID.strip())
        if current != allowed:
            if update.message:
                await update.message.delete()
                await update.message.reply_text("⛔ Доступ запрещён")
            else:
                await update.callback_query.answer("Доступ ограничен", show_alert=True)
            return False
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки доступа: {e}")
        return False

# ------------------------------
# Клавиатуры
# ------------------------------
def get_main_menu():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📊 Получить статистику"), KeyboardButton("ЛК ПП")],
         [KeyboardButton("⬅️ Назад")]], resize_keyboard=True
    )

def get_periods_keyboard(back_key="back_menu"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Сегодня", callback_data="period_today"),
         InlineKeyboardButton("7 дней", callback_data="period_7days"),
         InlineKeyboardButton("За месяц", callback_data="period_month")],
        [InlineKeyboardButton("Свой период", callback_data="period_custom")],
        [InlineKeyboardButton("Назад", callback_data=back_key)]
    ])

def get_metrics_keyboard(uniq_id: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✨ Рассчитать метрики", callback_data=f"metrics|{uniq_id}")],
        [InlineKeyboardButton("Обновить", callback_data=f"update|{uniq_id}"),
         InlineKeyboardButton("Назад", callback_data="back_periods")]
    ])

# ------------------------------
# Инициализация Telegram
# ------------------------------
async def init_telegram_app():
    logger.info("Инициализация Telegram-бота...")
    await telegram_app.initialize()
    await telegram_app.start()
    logger.info("Telegram-бот запущен!")

# ------------------------------
# Вебхук и постбек
# ------------------------------
@app.api_route("/webhook", methods=["GET", "POST"])
async def webhook_handler(request: Request):
    if request.method == "GET":
        return await process_postback_data(dict(request.query_params))
    data = await request.json()
    if "update_id" in data:
        update = Update.de_json(data, telegram_app.bot)
        if not await check_access(update):
            return {"status": "access_denied"}
        if not telegram_app.running:
            await init_telegram_app()
        await telegram_app.process_update(update)
        return {"status": "ok"}
    return await process_postback_data(data)

async def process_postback_data(data: dict):
    offer = data.get("offer_id", "N/A")
    goal = data.get("goal", "N/A")
    revenue = data.get("revenue", "N/A")
    sub3 = data.get("sub_id3", "N/A")
    msg = (
        f"🔔 <b>Новая конверсия!</b>\n\n"
        f"<b>📌 Оффер:</b> <i>{offer}</i>\n"
        f"<b>🛠 Подход:</b> <i>{sub3}</i>\n"
        f"<b>📊 Тип:</b> <i>{goal}</i>\n"
        f"<b>💰 Выплата:</b> <i>{revenue}</i>"
    )
    try:
        await telegram_app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="HTML")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Ошибка постбека: {e}")
        return {"status": "error"}

# ------------------------------
# Команды
# ------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    await update.message.reply_text("Привет! Выберите команду:", reply_markup=get_main_menu())

async def reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📊 Получить статистику":
        await update.message.reply_text("Выберите период:", reply_markup=get_periods_keyboard())
    elif text == "ЛК ПП":
        await update.message.reply_text("https://cabinet.4rabetpartner.com/statistics", reply_markup=get_main_menu())
    elif text == "⬅️ Назад":
        await update.message.reply_text("Главное меню:", reply_markup=get_main_menu())

# ------------------------------
# Вспомогательные функции
# ------------------------------
def get_dates(period: str):
    today = datetime.now().date()
    if period == "period_today": return today, today, "Сегодня"
    if period == "period_7days": return today - timedelta(days=6), today, "Последние 7 дней"
    if period == "period_month": return today - timedelta(days=29), today, "Последние 30 дней"
    return None, None, None

# ------------------------------
# Запросы к API
# ------------------------------
async def get_common(date_from: str, date_to: str):
    params = {"group_by": "day", "timezone": "Europe/Moscow",
              "date_from": date_from, "date_to": date_to, "currency_code": "USD"}
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_API_URL}/partner/statistic/common", headers={"API-KEY": API_KEY}, params=params)
    data = r.json().get("data", [])
    return {
        "click_count": sum(int(i.get("click_count",0)) for i in data),
        "click_unique": sum(int(i.get("click_unique_count",0)) for i in data),
        "conf_count": sum(int(i.get("conversions",{}).get("confirmed",{}).get("count",0)) for i in data),
        "conf_payout": sum(float(i.get("conversions",{}).get("confirmed",{}).get("payout",0)) for i in data)
    }

async def get_conversions(date_from: str, date_to: str):
    out = {"registration":0, "ftd":0, "rdeposit":0}
    page = 1
    while True:
        params = [("timezone","Europe/Moscow"),("date_from",date_from),("date_to",date_to),
                  ("per_page","500"),("page",str(page)),("group_by","day")]
        for key in out: params.append(("goal_keys[]", key))
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{BASE_API_URL}/partner/statistic/conversions", headers={"API-KEY": API_KEY}, params=params)
        data = r.json().get("data",[])
        if not data: break
        for item in data:
            k = item.get("goal",{}).get("key")
            if k in out: out[k] += 1
        page += 1
    return out

# ------------------------------
# Обработчик inline
# ------------------------------
async def inline_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    query = update.callback_query
    await query.answer()
    data = query.data
    if data in ["period_today","period_7days","period_month"]:
        start, end, label = get_dates(data)
        date_from, date_to = f"{start} 00:00", f"{end} 23:59"
        stats = await get_common(date_from.split()[0], date_to.split()[0])
        conv = await get_conversions(date_from, date_to)
        text = (
            f"📊 <b>Статистика</b> ({label})\n"
            f"🗓 <i>{start} .. {end}</i>\n"
            f"👁 {stats['click_count']} (уник: {stats['click_unique']})\n"
            f"🆕 Рег.: {conv['registration']} | FTD: {conv['ftd']} | RD: {conv['rdeposit']}\n"
            f"✅ Конверсии: {stats['conf_count']} | 💰 {stats['conf_payout']:.2f} USD"
        )
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_metrics_keyboard(str(uuid.uuid4())[:8]))
    elif data == "period_custom":
        await query.edit_message_text("🗓 Введите период (YYYY-MM-DD,YYYY-MM-DD)", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад",callback_data="back_menu")]]))
    elif data == "back_menu":
        await query.edit_message_text("Выберите период:", reply_markup=get_periods_keyboard())

# ------------------------------
# Регистрация хэндлеров
# ------------------------------
telegram_app.add_handler(CommandHandler("start", start_command))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_handler))
telegram_app.add_handler(CallbackQueryHandler(inline_handler))

# ------------------------------
# Запуск
# ------------------------------
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(init_telegram_app())
    import uvicorn; uvicorn.run(app, host="0.0.0.0", port=PORT)
