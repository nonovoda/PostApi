import os
import logging
import asyncio
from datetime import datetime, timedelta
import httpx
import json
import uuid
import sqlite3
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
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")  # 🔒 Должен быть числовой ID
DB_PATH = os.getenv("DB_PATH", "users.db")

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

# ------------------------------
# Инициализация базы данных
# ------------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
      user_id TEXT PRIMARY KEY,
      chat_id TEXT,
      is_approved INTEGER DEFAULT 0,
      awaiting_api INTEGER DEFAULT 0,
      api_key TEXT,
      postback_token TEXT UNIQUE,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()

init_db()

# ------------------------------
# 🔒 СИСТЕМА КОНТРОЛЯ ДОСТУПА
# ------------------------------
async def check_access(update: Update) -> bool:
    """Проверяет доступ по chat_id"""
    try:
        current_chat_id = int(update.effective_chat.id)
        allowed_chat_id = int(TELEGRAM_CHAT_ID.strip())
        
        logger.debug(f"Проверка доступа: {current_chat_id} vs {allowed_chat_id}")
        
        if current_chat_id != allowed_chat_id:
            logger.warning(f"🚨 Доступ запрещён для: {current_chat_id}")
            if update.message:
                await update.message.delete()
                await update.message.reply_text("⛔ Доступ запрещён")
            elif update.callback_query:
                await update.callback_query.answer("Доступ ограничен", show_alert=True)
            return False
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки доступа: {str(e)}")
        return False

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
# Webhook (Telegram + Postback)
# ------------------------------
@app.api_route("/webhook", methods=["GET", "POST"])
async def webhook_handler(request: Request):
    if request.method == "GET":
        data = dict(request.query_params)
        return await process_postback_data(data)
    
    try:
        data = await request.json()
        if "update_id" in data:
            update = Update.de_json(data, telegram_app.bot)
            
            # 🔒 Принудительная проверка доступа
            if not await check_access(update):
                return {"status": "access_denied"}
            
            if not telegram_app.running:
                await init_telegram_app()
            await telegram_app.process_update(update)
        else:
            return await process_postback_data(data)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
    
    return {"status": "ok"}

# ------------------------------
# Инициализация Telegram
# ------------------------------
async def init_telegram_app():
    logger.info("Инициализация Telegram-бота...")
    await telegram_app.initialize()
    await telegram_app.start()
    logger.info("Telegram-бот запущен!")

# ------------------------------
# Postback (конверсия)
# ------------------------------
async def process_postback_data(data: dict, chat_id=None):
    logger.debug(f"Postback data: {data}")
    offer_id = data.get("offer_id", "N/A")
    sub_id3 = data.get("sub_id3", "N/A")
    goal = data.get("goal", "N/A")
    revenue = data.get("revenue", "N/A")
    currency = data.get("currency", "USD")
    status = data.get("status", "N/A")
    sub_id4 = data.get("sub_id4", "N/A")
    sub_id5 = data.get("sub_id5", "N/A")
    cdate = data.get("conversion_date", "N/A")

    msg = (
        "🔔 <b>Новая конверсия!</b>\n\n"
        f"<b>📌 Оффер:</b> <i>{offer_id}</i>\n"
        f"<b>🛠 Подход:</b> <i>{sub_id3}</i>\n"
        f"<b>📊 Тип конверсии:</b> <i>{goal}</i>\n"
        f"<b>💰 Выплата:</b> <i>{revenue} {currency}</i>\n"
        f"<b>⚙️ Статус:</b> <i>{status}</i>\n"
        f"<b>🎯 Кампания:</b> <i>{sub_id4}</i>\n"
        f"<b>🎯 Адсет:</b> <i>{sub_id5}</i>\n"
        f"<b>⏰ Время конверсии:</b> <i>{cdate}</i>"
    )
    
    if not TELEGRAM_CHAT_ID:
        logger.error("TELEGRAM_CHAT_ID не задан в переменных окружения")
        return {"error": "Не настроен TELEGRAM_CHAT_ID"}, 500
    
    try:
        await telegram_app.bot.send_message(
            chat_id=chat_id or TELEGRAM_CHAT_ID,
            text=msg,
            parse_mode="HTML"
        )
        logger.debug("Postback-сообщение отправлено.")
    except Exception as e:
        logger.error(f"Ошибка при отправке postback: {e}")
        return {"error": "не удалось отправить сообщение"}, 500
    return {"status": "ok"}

# ------------------------------
# /start
# ------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 🔒 Проверка доступа
    if not await check_access(update):
        return

    txt = "Привет! Выберите команду:"
    mk = get_main_menu()
    await update.message.reply_text(txt, parse_mode="HTML", reply_markup=mk)

# ------------------------------
# Запрос доступа пользователя
# ------------------------------
async def request_access_handler(update, context):
    uid = str(update.effective_user.id)
    chat_id = str(update.effective_chat.id)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO users (user_id, chat_id, is_approved, awaiting_api)
        VALUES (?, ?, 0, 1)
    """, (uid, chat_id))
    conn.commit()
    conn.close()

    await update.message.reply_text("✅ Запрос отправлен. Ждите одобрения.")
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Одобрить", callback_data=f"access|approve|{uid}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"access|deny|{uid}")
    ]])
    await telegram_app.bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=f"📥 Новый запрос доступа от @{update.effective_user.username} ({uid})",
        reply_markup=kb
    )

telegram_app.add_handler(MessageHandler(filters.Regex("^🔑 Запросить доступ$"), request_access_handler), group=0)

# ------------------------------
# Inline-обработчик админа
# ------------------------------
async def admin_access_callback(update, context):
    q = update.callback_query
    await q.answer()
    _, action, uid = q.data.split("|")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    if action == "approve":
        cur.execute("UPDATE users SET is_approved=1, awaiting_api=1 WHERE user_id=?", (uid,))
        conn.commit()
        await telegram_app.bot.send_message(
            chat_id=uid,
            text="⚠️ Этот бот работает только с партнёрками на базе Alanbase.\nВведите ваш API-ключ для доступа."
        )
    else:  # deny
        cur.execute("DELETE FROM users WHERE user_id=?", (uid,))
        conn.commit()
        await telegram_app.bot.send_message(
            chat_id=uid,
            text="❌ Доступ отклонён."
        )

    conn.close()
    await q.edit_message_text(f"✅ Запрос {action} для {uid}")

telegram_app.add_handler(CallbackQueryHandler(admin_access_callback, pattern="^access\\|"))

# ------------------------------
# Хэндлер ввода API-ключа
# ------------------------------
async def api_key_handler(update, context):
    uid = str(update.effective_user.id)
    key = update.message.text.strip()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT awaiting_api FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()

    if not row or row[0] == 0:
        conn.close()
        return  # не в режиме ввода

    token = str(uuid.uuid4())[:8]
    cur.execute("""
        UPDATE users
        SET api_key=?, postback_token=?, awaiting_api=0
        WHERE user_id=?
    """, (key, token, uid))
    conn.commit()
    conn.close()

    link = f"https://yourbot.domain/webhook?token={token}&offer_id={{offer_id}}&sub_id3={{sub_id3}}&goal={{goal}}&revenue={{revenue}}&currency={{currency}}&status={{status}}&sub_id4={{sub_id4}}&sub_id5={{sub_id5}}&conversion_date={{conversion_date}}"
    await update.message.reply_text(
        f"✅ Ключ сохранён.\n\n🔗 Ваш Postback URL:\n<code>{link}</code>",
        parse_mode="HTML", reply_markup=get_main_menu()
    )

telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, api_key_handler), group=1)

# ------------------------------
# Запуск приложения
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    loop = asyncio.get_event_loop()
    loop.create_task(init_telegram_app())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
