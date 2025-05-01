import os
import logging
import asyncio
from datetime import datetime, timedelta
import httpx
import json
import uuid
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
BASE_API_URL = "https://4rabet.api.alanbase.com/v1"
PORT = int(os.environ.get("PORT", 8000))
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

# ------------------------------
# 🔒 СИСТЕМА КОНТРОЛЯ ДОСТУПА
# ------------------------------
async def check_access(update: Update) -> bool:
    """Проверяет доступ по chat_id"""
    try:
        current_id = int(update.effective_chat.id)
        allowed_id = int(TELEGRAM_CHAT_ID.strip())
        logger.debug(f"Проверка доступа: {current_id} vs {allowed_id}")
        if current_id != allowed_id:
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
# Универсальные клавиатуры
# ------------------------------
def main_menu():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📊 Получить статистику"), KeyboardButton("ЛК ПП")],
         [KeyboardButton("⬅️ Назад")]],
        resize_keyboard=True
    )

_periods_kb = [
    [InlineKeyboardButton("Сегодня", callback_data="period_today"),
     InlineKeyboardButton("7 дней", callback_data="period_7days"),
     InlineKeyboardButton("За месяц", callback_data="period_month")],
    [InlineKeyboardButton("Свой период", callback_data="period_custom")],
]

def periods_keyboard(back_key="back_menu"):
    kb = _periods_kb.copy()
    kb.append([InlineKeyboardButton("Назад", callback_data=back_key)])
    return InlineKeyboardMarkup(kb)

_metrics_buttons = lambda uid: [
    [InlineKeyboardButton("✨ Рассчитать метрики", callback_data=f"metrics|{uid}")],
    [InlineKeyboardButton("Обновить", callback_data=f"update|{uid}"),
     InlineKeyboardButton("Назад", callback_data="back_periods")]
]

def metrics_keyboard(uid):
    return InlineKeyboardMarkup(_metrics_buttons(uid))

# ------------------------------
# Инициализация Telegram
# ------------------------------
async def init_telegram():
    logger.info("Запуск Telegram бота...")
    await telegram_app.initialize()
    await telegram_app.start()
    logger.info("Telegram бот запущен")

# ------------------------------
# Webhook и Postback
# ------------------------------
@app.api_route("/webhook", methods=["GET","POST"])
async def webhook(request: Request):
    if request.method == "GET":
        return await process_postback(dict(request.query_params))
    data = await request.json()
    if "update_id" in data:
        update = Update.de_json(data, telegram_app.bot)
        if not await check_access(update): return {"status":"denied"}
        if not telegram_app.running:
            await init_telegram()
        await telegram_app.process_update(update)
        return {"status":"ok"}
    return await process_postback(data)

async def process_postback(data: dict):
    logger.debug(f"Postback: {data}")
    fields = ["offer_id","sub_id3","goal","revenue","currency",
              "status","sub_id4","sub_id5","conversion_date"]
    vals = {f:data.get(f,"N/A") for f in fields}
    msg = (
        f"🔔 <b>Новая конверсия!</b>\n"
        f"📌 <i>Оффер:</i> {vals['offer_id']}\n"
        f"🛠 <i>Подход:</i> {vals['sub_id3']}\n"
        f"📊 <i>Тип:</i> {vals['goal']}\n"
        f"💰 <i>Выплата:</i> {vals['revenue']} {vals['currency']}\n"
        f"⚙️ <i>Статус:</i> {vals['status']}\n"
        f"🎯 <i>Кампания:</i> {vals['sub_id4']}\n"
        f"🎯 <i>Адсет:</i> {vals['sub_id5']}\n"
        f"⏰ <i>Время:</i> {vals['conversion_date']}"
    )
    try:
        await telegram_app.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID, text=msg, parse_mode="HTML"
        )
        return {"status":"ok"}
    except Exception as e:
        logger.error(f"Postback send error: {e}")
        return {"status":"error"}

# ------------------------------
# Команды
# ------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    await update.message.reply_text("Привет!", reply_markup=main_menu())

async def reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    txt = update.message.text
    if txt == "📊 Получить статистику":
        await update.message.reply_text("Выберите период:", reply_markup=periods_keyboard())
    elif txt == "ЛК ПП":
        await update.message.reply_text("https://cabinet.4rabetpartner.com/statistics", reply_markup=main_menu())
    elif txt == "⬅️ Назад":
        await update.message.reply_text("Главное меню:", reply_markup=main_menu())

# ------------------------------
# Вспомогательное: даты по ключу
# ------------------------------
def get_period_range(key: str):
    today = datetime.now().date()
    if key == "period_today": return today, today, "Сегодня"
    if key == "period_7days": return today - timedelta(days=6), today, "Последние 7 дней"
    if key == "period_month": return today - timedelta(days=29), today, "Последние 30 дней"
    return None, None, None

# ------------------------------
# Запросы к API
# ------------------------------
async def fetch_common(start: str, end: str):
    params = {"group_by":"day","timezone":"Europe/Moscow",
              "date_from":start,"date_to":end,"currency_code":"USD"}
    async with httpx.AsyncClient(timeout=30) as c:
        resp = await c.get(f"{BASE_API_URL}/partner/statistic/common", headers={"API-KEY":API_KEY}, params=params)
    data = resp.json().get("data",[])
    clicks = sum(int(i.get("click_count",0)) for i in data)
    unique = sum(int(i.get("click_unique_count",0)) for i in data)
    conv = sum(int(i.get("conversions",{}).get("confirmed",{}).get("count",0)) for i in data)
    payout = sum(float(i.get("conversions",{}).get("confirmed",{}).get("payout",0)) for i in data)
    return clicks, unique, conv, payout

async def fetch_conversions(start: str, end: str):
    out = {"registration":0,"ftd":0,"rdeposit":0}
    page = 1
    while True:
        params = [("timezone","Europe/Moscow"),("date_from",start),("date_to",end),
                  ("per_page","500"),("page",str(page)),("group_by","day")]
        for k in out: params.append(("goal_keys[]",k))
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"{BASE_API_URL}/partner/statistic/conversions", headers={"API-KEY":API_KEY}, params=params)
        arr = r.json().get("data",[])
        if not arr: break
        for it in arr:
            key = it.get("goal",{}).get("key")
            if key in out: out[key]+=1
        page+=1
    return out["registration"], out["ftd"], out["rdeposit"]

# ------------------------------
# Inline Handler
# ------------------------------
async def inline_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update): return
    q = update.callback_query
    await q.answer()
    data = q.data
    if data in ("period_today","period_7days","period_month"):
        st, ed, lbl = get_period_range(data)
        df, dt = f"{st} 00:00", f"{ed} 23:59"
        clicks, uniq, conv_count, payout = await fetch_common(df.split()[0], dt.split()[0])
        reg, ftd, rd = await fetch_conversions(df, dt)
        date_lbl = f"{st} .. {ed}"
        text = (
            f"📊 <b>Статистика</b> ({lbl})\n\n"
            f"🗓 <i>{date_lbl}</i>\n\n"
            f"👁 <i>Клики:</i> {clicks} (уник: {uniq})\n"
            f"🆕 <i>Регистрации:</i> {reg}\n"
            f"💵 <i>FTD:</i> {ftd}\n"
            f"🔄 <i>RD:</i> {rd}\n\n"
            f"✅ <i>Конверсии:</i> {conv_count}\n"
            f"💰 <i>Доход:</i> {payout:.2f} USD"
        )
        uid = str(uuid.uuid4())[:8]
        context.user_data.setdefault("stats_store", {})[uid] = {
            "base_text": text, "clicks": clicks, "unique": uniq,
            "reg": reg, "ftd": ftd, "rd": rd,
            "date_from": df, "date_to": dt, "label": lbl,
            "conf_count": conv_count, "conf_payout": payout
        }
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=metrics_keyboard(uid))
    elif data == "period_custom":
        await q.edit_message_text(
            "🗓 Введите период (YYYY-MM-DD,YYYY-MM-DD)",
            parse_mode="HTML", reply_markup=periods_keyboard(back_key="back_periods")
        )
        context.user_data["awaiting_period"] = True
        context.user_data["inline_msg_id"] = q.message.message_id
    elif data == "back_menu":
        await q.edit_message_text("Выберите период:", reply_markup=periods_keyboard())
    elif data == "back_periods":
        await q.edit_message_text("Выберите период:", reply_markup=periods_keyboard())
    elif data.startswith("metrics|"):
        uid = data.split("|")[1]
        store = context.user_data.get("stats_store", {}).get(uid)
        if not store: return await q.edit_message_text("❗ Данные не найдены")
        metrics_txt = build_metrics(
            store['clicks'], store['unique'], store['reg'],
            store['ftd'], store['conf_payout'], store['rd']
        )
        await q.edit_message_text(
            store['base_text'] + "\n" + metrics_txt,
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Скрыть метрики", callback_data=f"hide|{uid}")],
                [InlineKeyboardButton("Обновить", callback_data=f"update|{uid}"),
                 InlineKeyboardButton("Назад", callback_data="back_periods")]            ])
        )
    elif data.startswith("hide|"):
        uid = data.split("|")[1]
        base = context.user_data.get("stats_store", {}).get(uid, {}).get('base_text', '')
        await q.edit_message_text(base, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✨ Рассчитать метрики", callback_data=f"metrics|{uid}" )],
            [InlineKeyboardButton("Обновить", callback_data=f"update|{uid}"),
             InlineKeyboardButton("Назад", callback_data="back_periods")]
        ]))
    elif data.startswith("update|"):
        uid = data.split("|")[1]
        s = context.user_data.get("stats_store", {}).get(uid)
        if not s: return await q.edit_message_text("❗ Ошибка параметров обновления")
        await inline_handler(update, context)

# ------------------------------
# Хэндлер ввода текста (custom period)
# ------------------------------
async def period_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update) or not context.user_data.get("awaiting_period"): return
    txt = update.message.text.strip()
    msg_id = context.user_data.get("inline_msg_id")
    try: await update.message.delete()
    except: pass
    if txt.lower() == "назад":
        context.user_data.pop("awaiting_period", None)
        return await telegram_app.bot.edit_message_text(
            chat_id=update.effective_chat.id, message_id=msg_id,
            text="Выберите период:", reply_markup=periods_keyboard()
        )
    try:
        st, ed = [datetime.strptime(d.strip(), "%Y-%m-%d").date() for d in txt.split(",")]
    except:
        return await update.message.reply_text("❗ Формат YYYY-MM-DD,YYYY-MM-DD или 'Назад'")
    if st > ed:
        return await update.message.reply_text("❗ Начальная дата больше конечной.")
    df, dt = f"{st} 00:00", f"{ed} 23:59"
    context.user_data.pop("awaiting_period", None)
    return await inline_handler(Update.callback_query(update), context)

# ------------------------------
# Регистрация хэндлеров
# ------------------------------
telegram_app.add_handler(CommandHandler("start", start_cmd))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_handler), group=1)
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, period_text_handler), group=2)
telegram_app.add_handler(CallbackQueryHandler(inline_handler))

# ------------------------------
# Запуск приложения
# ------------------------------
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(init_telegram())
    import uvicorn; uvicorn.run(app, host="0.0.0.0", port=PORT)
