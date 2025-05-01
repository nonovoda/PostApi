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
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")
DB_PATH = os.getenv("DB_PATH", "users.db")

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# ------------------------------
# Инициализация
# ------------------------------
app = FastAPI()
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

# ------------------------------
# SQLite: таблица users
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

def get_db():
    return sqlite3.connect(DB_PATH)

def get_user_status(user_id):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT is_approved, awaiting_api FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row if row else (0, 0)

# ------------------------------
# 🔒 Система контроля доступа
# ------------------------------
async def check_access(update: Update) -> bool:
    try:
        current_chat_id = int(update.effective_chat.id)
        allowed_chat_id = int(os.getenv("TELEGRAM_CHAT_ID", "0"))

        # Разрешаем кнопку запроса доступа
        if update.message and update.message.text == "🔑 Запросить доступ":
            return True

        if current_chat_id != allowed_chat_id:
            logger.warning(f"🚨 Доступ запрещён для: {current_chat_id}")
            if update.message:
                await update.message.delete()
                await update.message.reply_text(
                    "⛔ У вас нет доступа. Нажмите «🔑 Запросить доступ».",
                    reply_markup=ReplyKeyboardMarkup(
                        [[KeyboardButton("🔑 Запросить доступ")]],
                        resize_keyboard=True
                    )
                )
            elif update.callback_query:
                await update.callback_query.answer("⛔ У вас нет доступа.", show_alert=True)
            return False
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки доступа: {str(e)}")
        return False

# ------------------------------
# Главное меню
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
# Хэндлер /start
# ------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    chat = str(update.effective_chat.id)
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users(user_id,chat_id) VALUES(?,?)", (uid, chat))
    conn.commit(); conn.close()
    await update.message.reply_text("👋 Привет! Выберите команду:", reply_markup=get_main_menu())

# ------------------------------
# Хэндлер «Запросить доступ»
# ------------------------------
async def request_access_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)  # ID пользователя
    chat_id = str(update.effective_chat.id)  # ID чата
    user_name = update.effective_user.username  # Имя пользователя
    
    # Добавляем пользователя в базу данных (запрашивающий доступ)
    conn = get_db()  # Подключаемся к базе данных
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO users(user_id, chat_id, awaiting_api)
        VALUES(?, ?, 1)
    """, (user_id, chat_id))  # Помечаем пользователя как ожидающего доступа
    conn.commit()
    conn.close()

    # Отправляем пользователю подтверждение, что запрос на доступ отправлен
    await update.message.reply_text("✅ Ваш запрос на доступ отправлен. Ожидайте одобрения.")

    # Отправляем сообщение с запросом на одобрение в основной чат (например, к вам)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Одобрить", callback_data=f"access|approve|{user_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"access|deny|{user_id}")
    ]])

    # Отправка сообщения в ваш чат с кнопками для одобрения/отклонения
    await telegram_app.bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,  # Ваш ID чата, куда отправляется запрос
        text=f"📥 Новый запрос доступа от @{user_name} ({user_id})",
        reply_markup=kb
    )

# Хэндлер для кнопок "Одобрить" или "Отклонить"
async def access_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    action, user_id = data.split("|")[1:]  # Разделяем действие (одобрить/отклонить) и user_id

    # Получаем информацию о пользователе
    conn = get_db()
    cur = conn.cursor()

    # Если действие "одобрить"
    if action == "approve":
        cur.execute("""
            UPDATE users SET is_approved = 1 WHERE user_id = ?
        """, (user_id,))
        conn.commit()
        conn.close()
        await query.answer("✅ Доступ одобрен!")
        await query.edit_message_text("Доступ был одобрен.")
    # Если действие "отклонить"
    elif action == "deny":
        cur.execute("""
            UPDATE users SET is_approved = 0 WHERE user_id = ?
        """, (user_id,))
        conn.commit()
        conn.close()
        await query.answer("❌ Доступ отклонён!")
        await query.edit_message_text("Доступ был отклонён.")
    
    # Уведомление пользователю о решении
    await telegram_app.bot.send_message(
        chat_id=user_id,
        text=f"Ваш запрос на доступ был {('одобрен', 'отклонён')[action == 'deny']}. Спасибо за обращение!"
    )

# ------------------------------
# Inline-коллбэк админа
# ------------------------------
async def admin_access_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, action, uid = q.data.split("|")
    conn = get_db(); cur = conn.cursor()
    if action == "approve":
        cur.execute("UPDATE users SET is_approved=1,awaiting_api=1 WHERE user_id=?", (uid,))
        conn.commit()
        await telegram_app.bot.send_message(
            chat_id=uid,
            text="⚠️ Этот бот работает только с партнёрками Alanbase.\nВведите ваш API-ключ:"
        )
        res = "Одобрено"
    else:
        cur.execute("DELETE FROM users WHERE user_id=?", (uid,))
        conn.commit()
        await telegram_app.bot.send_message(chat_id=uid, text="❌ Доступ отклонён.")
        res = "Отклонено"
    conn.close()
    await q.edit_message_text(f"{res} для {uid}")

# ------------------------------
# Хэндлер ввода API-ключа
# ------------------------------
async def api_key_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    text = update.message.text.strip()
    is_approved, awaiting = get_user_status(uid)
    if awaiting != 1:
        return  # не ожидаем ключ
    token = str(uuid.uuid4())[:8]
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        UPDATE users
        SET api_key=?, postback_token=?, awaiting_api=0
        WHERE user_id=?
    """, (text, token, uid))
    conn.commit(); conn.close()
    link = (
        f"https://your.domain/webhook?token={token}"
        "&offer_id={offer_id}&sub_id3={sub_id3}&goal={goal}"
        "&revenue={revenue}&currency={currency}&status={status}"
        "&sub_id4={sub_id4}&sub_id5={sub_id5}&conversion_date={conversion_date}"
    )
    await update.message.reply_text(
        f"✅ API-ключ сохранён.\n\n🔗 Ваш Postback URL:\n<code>{link}</code>\n\n"
        "sub_id3 — подход, sub_id4 — кампания, sub_id5 — адсет",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )

# ------------------------------
# Изменённый Webhook для постбеков
# ------------------------------
@app.api_route("/webhook", methods=["GET", "POST"])
async def webhook_handler(request: Request):
    # GET — по токену
    if request.method == "GET":
        params = dict(request.query_params)
        token = params.get("token")
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT chat_id FROM users WHERE postback_token=?", (token,))
        row = cur.fetchone(); conn.close()
        if not row:
            return {"status": "unauthorized"}
        return await process_postback_data(params, chat_id=row[0])

    # POST — для Telegram
    data = await request.json()
    if "update_id" in data:
        update = Update.de_json(data, telegram_app.bot)
        if not await check_access(update):
            return {"status": "access_denied"}
        if not telegram_app.running:
            await init_telegram_app()
        await telegram_app.process_update(update)
        return {"status": "ok"}
    else:
        return await process_postback_data(data)

# ------------------------------
# process_postback_data (не меняем ваш текст)
# ------------------------------
async def process_postback_data(data: dict, chat_id=None):
    # ... (ваша оригинальная реализация) ...
    await telegram_app.bot.send_message(chat_id=chat_id or TELEGRAM_CHAT_ID, text="🔔 Новая конверсия!", parse_mode="HTML")
    return {"status": "ok"}

async def process_postback_data(data: dict):
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
            chat_id=TELEGRAM_CHAT_ID,
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

# Агрегация для /common (ИСПРАВЛЕННАЯ ВЕРСИЯ)
# ------------------------------
async def get_common_data_aggregated(date_from: str, date_to: str):
    try:
        logger.info(f"Запрос /common за период: {date_from} - {date_to}")
        
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{BASE_API_URL}/partner/statistic/common",
                headers={"API-KEY": API_KEY},
                params={
                    "group_by": "day",
                    "timezone": "Europe/Moscow",
                    "date_from": date_from.split()[0],  # Берем только дату
                    "date_to": date_to.split()[0],      # Без времени
                    "currency_code": "USD"
                }
            )

        if r.status_code != 200:
            return False, f"Ошибка /common {r.status_code}: {r.text}"
        
        data = r.json()
        arr = data.get("data", [])
        
        logger.debug(f"Сырые данные API: {json.dumps(arr, ensure_ascii=False)}")
        
        # Обнуляем счетчики
        total = {
            "click_count": 0,
            "click_unique": 0,
            "conf_count": 0,
            "conf_payout": 0.0
        }
        
        for item in arr:
            total["click_count"] += int(item.get("click_count", 0))
            total["click_unique"] += int(item.get("click_unique_count", 0))
            
            conversions = item.get("conversions", {})
            confirmed = conversions.get("confirmed", {})
            
            # Проверка типа данных для конверсий
            if isinstance(confirmed, dict):
                total["conf_count"] += int(confirmed.get("count", 0))
                total["conf_payout"] += float(confirmed.get("payout", 0))
            else:
                logger.warning(f"Некорректный формат конверсий: {type(confirmed)}")

        logger.info(f"Итоговая агрегация: {total}")
        return True, total
        
    except Exception as e:
        logger.error(f"Критическая ошибка в get_common_data_aggregated: {str(e)}")
        return False, f"Ошибка обработки данных: {str(e)}"

# ------------------------------
# Агрегация для /conversions (registration, ftd, rdeposit)
# ------------------------------
async def get_rfr_aggregated(date_from: str, date_to: str):
    out = {"registration": 0, "ftd": 0, "rdeposit": 0}
    page = 1
    goal_keys = ["registration", "ftd", "rdeposit"]

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                params = [
                    ("timezone", "Europe/Moscow"),
                    ("date_from", date_from),
                    ("date_to", date_to),
                    ("per_page", "500"),
                    ("page", str(page)),
                    ("group_by", "day")
                ]
                for key in goal_keys:
                    params.append(("goal_keys[]", key))

                resp = await client.get(
                    f"{BASE_API_URL}/partner/statistic/conversions",
                    headers={"API-KEY": API_KEY},
                    params=params
                )

                if resp.status_code != 200:
                    return False, f"Ошибка /conversions {resp.status_code}: {resp.text}"

                arr = resp.json().get("data", [])
                if not arr:
                    break  # нет данных — завершаем

                for c in arr:
                    g = c.get("goal", {}).get("key")
                    if g in out:
                        out[g] += 1

                page += 1  # следующая страница

        return True, out
    except Exception as e:
        return False, str(e)

# ------------------------------
# Формирование итогового текста статистики
# ------------------------------
def build_stats_text(label, date_label, clicks, unique_clicks, reg_count, ftd_count, rd_count, conf_count, conf_payout):
    return (
        f"📊 <b>Статистика</b> ({label})\n\n"
        f"🗓 <b>Период:</b> <i>{date_label}</i>\n\n"
        f"👁 <b>Клики:</b> <i>{clicks}</i> (уник: {unique_clicks})\n"
        f"🆕 <b>Регистрации:</b> <i>{reg_count}</i>\n"
        f"💵 <b>FTD:</b> <i>{ftd_count}</i>\n"
        f"🔄 <b>RD:</b> <i>{rd_count}</i>\n\n"
        f"✅ <b>Конверсии:</b> <i>{conf_count}</i>\n"
        f"💰 <b>Доход:</b> <i>{conf_payout:.2f} USD</i>\n"
    )

# ------------------------------
# Формирование метрик
# ------------------------------
def build_metrics(clicks, unique_clicks, reg, ftd, conf_payout, rd):
    c2r = (reg / clicks * 100) if clicks > 0 else 0
    r2d = (ftd / reg * 100) if reg > 0 else 0
    c2d = (ftd / clicks * 100) if clicks > 0 else 0
    fd2rd = (rd / ftd * 100) if ftd > 0 else 0
    epc = (conf_payout / clicks) if clicks > 0 else 0
    uepc = (conf_payout / unique_clicks) if unique_clicks > 0 else 0
    return (
        "🎯 <b>Метрики:</b>\n\n"
        f"• <b>C2R</b> = {c2r:.2f}%\n"
        f"• <b>R2D</b> = {r2d:.2f}%\n"
        f"• <b>C2D</b> = {c2d:.2f}%\n"
        f"• <b>FD2RD</b> = {fd2rd:.2f}%\n\n"
        f"• <b>EPC</b> = {epc:.3f} USD\n"
        f"• <b>uEPC</b> = {uepc:.3f} USD\n"
    )

# ------------------------------
# Inline-хэндлер для кнопок
# ------------------------------
async def inline_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update):
        await update.callback_query.answer("Доступ запрещён", show_alert=True)
        return

    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back_menu":
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Сегодня", callback_data="period_today"),
                InlineKeyboardButton("7 дней", callback_data="period_7days"),
                InlineKeyboardButton("За месяц", callback_data="period_month")
            ],
            [InlineKeyboardButton("Свой период", callback_data="period_custom")],
            [InlineKeyboardButton("Назад", callback_data="back_menu")]
        ])
        await query.edit_message_text("Выберите период:", parse_mode="HTML", reply_markup=kb)
        return

    elif data in ["period_today", "period_7days", "period_month"]:
        if data == "period_today":
            d_str = datetime.now().strftime("%Y-%m-%d")
            date_from = f"{d_str} 00:00"
            date_to = f"{d_str} 23:59"
            label = "Сегодня"
        elif data == "period_7days":
            end_ = datetime.now().date()
            start_ = end_ - timedelta(days=6)
            date_from = f"{start_} 00:00"
            date_to = f"{end_} 23:59"
            label = "Последние 7 дней"
        elif data == "period_month":
            end_ = datetime.now().date()
            start_ = end_ - timedelta(days=29)
            date_from = f"{start_} 00:00"
            date_to = f"{end_} 23:59"
            label = "Последние 30 дней"
        await show_stats_screen(query, context, date_from, date_to, label)
        return

    elif data == "period_custom":
        txt = (
            "🗓 Введите период (YYYY-MM-DD,YYYY-MM-DD)\n"
            "Пример: 2025-02-01,2025-02-10\n"
            "Нажмите 'Назад', чтобы вернуться."
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Назад", callback_data="back_periods")]
        ])
        await query.edit_message_text(txt, parse_mode="HTML", reply_markup=kb)
        context.user_data["awaiting_period"] = True
        context.user_data["inline_msg_id"] = query.message.message_id
        return

    elif data == "back_periods":
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Сегодня", callback_data="period_today"),
                InlineKeyboardButton("7 дней", callback_data="period_7days"),
                InlineKeyboardButton("За месяц", callback_data="period_month")
            ],
            [InlineKeyboardButton("Свой период", callback_data="period_custom")],
            [InlineKeyboardButton("Назад", callback_data="back_menu")]
        ])
        await query.edit_message_text("Выберите период:", parse_mode="HTML", reply_markup=kb)
        return

    elif data.startswith("metrics|"):
        uniq_id = data.split("|")[1]
        store = context.user_data.get("stats_store", {}).get(uniq_id)
        if not store:
            await query.edit_message_text("❗ Данные не найдены", parse_mode="HTML")
            return
        base_text = store["base_text"]
        c_ = store["clicks"]
        uc_ = store["unique"]
        r_ = store["reg"]
        f_ = store["ftd"]
        rd_ = store["rd"]
        confp = store["confp"]
        metrics_txt = build_metrics(c_, uc_, r_, f_, confp, rd_)
        final_txt = base_text + "\n" + metrics_txt
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Скрыть метрики", callback_data=f"hide|{uniq_id}")],
            [InlineKeyboardButton("Обновить", callback_data=f"update|{uniq_id}")],
            [InlineKeyboardButton("Назад", callback_data="back_periods")]
        ])
        await query.edit_message_text(final_txt, parse_mode="HTML", reply_markup=kb)
        return

    elif data.startswith("hide|"):
        uniq_id = data.split("|")[1]
        st_ = context.user_data.get("stats_store", {}).get(uniq_id)
        if not st_:
            await query.edit_message_text("❗ Данные не найдены", parse_mode="HTML")
            return
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✨ Рассчитать метрики", callback_data=f"metrics|{uniq_id}")],
            [InlineKeyboardButton("Обновить", callback_data=f"update|{uniq_id}")],
            [InlineKeyboardButton("Назад", callback_data="back_periods")]
        ])
        await query.edit_message_text(st_["base_text"], parse_mode="HTML", reply_markup=kb)
        return

    elif data.startswith("update|"):
        uniq_id = data.split("|")[1]
        store = context.user_data.get("stats_store", {}).get(uniq_id)
        if not store:
            await query.edit_message_text("❗ Данные не найдены", parse_mode="HTML")
            return
        date_from = store.get("date_from")
        date_to = store.get("date_to")
        label = store.get("label")
        if not (date_from and date_to and label):
            await query.edit_message_text("❗ Ошибка параметров обновления", parse_mode="HTML")
            return
        await show_stats_screen(query, context, date_from, date_to, label)
        return

    await query.edit_message_text("Неизвестная команда", parse_mode="HTML")

# ------------------------------
# Показ статистики
# ------------------------------
async def show_stats_screen(query, context, date_from: str, date_to: str, label: str):
    okc, cinfo = await get_common_data_aggregated(date_from, date_to)
    if not okc:
        text = f"❗ {cinfo}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_periods")]])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        return
    cc = cinfo["click_count"]
    uc = cinfo["click_unique"]
    confc = cinfo["conf_count"]
    confp = cinfo["conf_payout"]

    okr, rdata = await get_rfr_aggregated(date_from, date_to)
    if not okr:
        text = f"❗ {rdata}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_periods")]])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        return
    reg = rdata["registration"]
    ftd = rdata["ftd"]
    rd = rdata["rdeposit"]

    date_lbl = f"{date_from[:10]} .. {date_to[:10]}"
    base_text = build_stats_text(label, date_lbl, cc, uc, reg, ftd, rd, confc, confp)

    if "stats_store" not in context.user_data:
        context.user_data["stats_store"] = {}
    uniq_id = str(uuid.uuid4())[:8]
    context.user_data["stats_store"][uniq_id] = {
        "base_text": base_text,
        "clicks": cc,
        "unique": uc,
        "reg": reg,
        "ftd": ftd,
        "rd": rd,
        "date_from": date_from,
        "date_to": date_to,
        "label": label,
        "confp": confp
    }

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✨ Рассчитать метрики", callback_data=f"metrics|{uniq_id}")],
        [InlineKeyboardButton("Обновить", callback_data=f"update|{uniq_id}")],
        [InlineKeyboardButton("Назад", callback_data="back_periods")]
    ])
    await query.edit_message_text(base_text, parse_mode="HTML", reply_markup=kb)

# ------------------------------
# Хэндлер ввода дат (Свой период)
# ------------------------------

async def period_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 🔒 Проверка доступа
    if not await check_access(update):
        return
    
    if not context.user_data.get("awaiting_period"):
        return
    
    try:
        await update.message.delete()
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение: {e}")
    
    txt = update.message.text.strip()
    logger.info(f"Ввод периода: {txt}")
    
    if txt.lower() == "назад":
        context.user_data["awaiting_period"] = False
        inline_id = context.user_data.get("inline_msg_id")
        if inline_id:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("Сегодня", callback_data="period_today"),
                 InlineKeyboardButton("7 дней", callback_data="period_7days"),
                 InlineKeyboardButton("За месяц", callback_data="period_month")],
                [InlineKeyboardButton("Свой период", callback_data="period_custom")],
                [InlineKeyboardButton("Назад", callback_data="back_menu")]
            ])
            await telegram_app.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=inline_id,
                text="Выберите период:",
                parse_mode="HTML",
                reply_markup=kb
            )
        context.user_data.pop("inline_msg_id", None)
        context.user_data["awaiting_period"] = False
        return
    
    parts = txt.split(",")
    if len(parts) != 2:
        await update.message.reply_text("❗ Формат: YYYY-MM-DD,YYYY-MM-DD или 'Назад'")
        context.user_data["awaiting_period"] = False
        return
    
    try:
        st_d = datetime.strptime(parts[0].strip(), "%Y-%m-%d").date()
        ed_d = datetime.strptime(parts[1].strip(), "%Y-%m-%d").date()
    except:
        await update.message.reply_text("❗ Ошибка разбора дат.")
        context.user_data["awaiting_period"] = False
        return
    
    if st_d > ed_d:
        await update.message.reply_text("❗ Начальная дата больше конечной.")
        context.user_data["awaiting_period"] = False
        return
    
    # Корректный ввод: обновляем статистику
    context.user_data["awaiting_period"] = False
    inline_id = context.user_data.pop("inline_msg_id", None)
    
    # Убедимся, что inline_id существует
    if not inline_id:
        await update.message.reply_text("❗ Не удалось найти сообщение для обновления.")
        return
    
    date_from = f"{st_d} 00:00"
    date_to = f"{ed_d} 23:59"
    lbl = "Свой период"
    
    # Используем chat_id из текущего сообщения для редактирования
    chat_id = update.effective_chat.id
    try:
        await show_stats_screen(update.callback_query, context, date_from, date_to, lbl)
    except AttributeError:
        # Если это не callback_query, создаем FakeQ с chat_id и inline_id
        fquery = FakeQ(inline_id, chat_id)
        await show_stats_screen(fquery, context, date_from, date_to, lbl)


# ------------------------------
# Reply-хэндлер для текстовых команд
# ------------------------------
async def reply_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 🔒 Проверка доступа
    if not await check_access(update):
        return

    text = update.message.text.strip()
    known_commands = ["📊 Получить статистику", "ЛК ПП", "⬅️ Назад"]
    
    if text not in known_commands:
        return  # Игнорируем неизвестные команды
    
    try:
        await update.message.delete()
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение: {e}")
    
    if text == "ЛК ПП":
        link = "Ваш личный кабинет: https://cabinet.4rabetpartner.com/statistics"
        await update.message.reply_text(link, parse_mode="HTML", reply_markup=get_main_menu())
    elif text == "📊 Получить статистику":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Сегодня", callback_data="period_today"),
             InlineKeyboardButton("7 дней", callback_data="period_7days"),
             InlineKeyboardButton("За месяц", callback_data="period_month")],
            [InlineKeyboardButton("Свой период", callback_data="period_custom")],
            [InlineKeyboardButton("Назад", callback_data="back_menu")]
        ])
        await update.message.reply_text("Выберите период:", parse_mode="HTML", reply_markup=kb)
    elif text == "⬅️ Назад":
        mk = get_main_menu()
        await update.message.reply_text("Главное меню:", parse_mode="HTML", reply_markup=mk)
    else:
        await update.message.reply_text("Неизвестная команда", parse_mode="HTML", reply_markup=get_main_menu())

# ------------------------------
# FakeQ класс
# ------------------------------
class FakeQ:
    def __init__(self, msg_id, chat_id):
        self.message = type("Msg", (), {})()
        self.message.message_id = msg_id
        self.message.chat_id = chat_id

    async def edit_message_text(self, *args, **kwargs):
        return await telegram_app.bot.edit_message_text(
            chat_id=self.message.chat_id,
            message_id=self.message.message_id,
            *args, **kwargs
        )

    async def answer(self):
        pass
# ------------------------------
# Регистрация новых хэндлеров
# ------------------------------
telegram_app.add_handler(CommandHandler("start", start_command))
telegram_app.add_handler(MessageHandler(filters.Regex("^🔑 Запросить доступ$"), request_access_handler), group=0)
telegram_app.add_handler(CallbackQueryHandler(admin_access_callback, pattern="^access\\|"))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, api_key_handler), group=1)
telegram_app.add_handler(CommandHandler("start", start_command))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, period_text_handler), group=1)
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_button_handler), group=2)
telegram_app.add_handler(CallbackQueryHandler(inline_handler))

# ------------------------------
# Запуск приложения
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    loop = asyncio.get_event_loop()
    loop.create_task(init_telegram_app())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
