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
# Система контроля доступа
# ------------------------------
async def check_access(update: Update) -> bool:
    """Проверяет доступ по chat_id"""
    try:
        current_chat_id = int(update.effective_chat.id)
        allowed_chat_id = int(TELEGRAM_CHAT_ID.strip())
        
        if current_chat_id != allowed_chat_id:
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
# Универсальные клавиатуры
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

def get_periods_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Сегодня", callback_data="period_today"),
            InlineKeyboardButton("7 дней", callback_data="period_7days"),
            InlineKeyboardButton("За месяц", callback_data="period_month")
        ],
        [InlineKeyboardButton("Свой период", callback_data="period_custom")],
        [InlineKeyboardButton("Назад", callback_data="back_menu")]
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
# Получение данных с API
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
                    "date_from": date_from.split()[0],
                    "date_to": date_to.split()[0],
                    "currency_code": "USD"
                }
            )

        if r.status_code != 200:
            return False, f"Ошибка /common {r.status_code}: {r.text}"
        
        data = r.json()
        arr = data.get("data", [])
        total = {
            "click_count": sum(int(item.get("click_count", 0)) for item in arr),
            "click_unique": sum(int(item.get("click_unique_count", 0)) for item in arr),
            "conf_count": sum(int(item.get("conversions", {}).get("confirmed", {}).get("count", 0)) for item in arr),
            "conf_payout": sum(float(item.get("conversions", {}).get("confirmed", {}).get("payout", 0)) for item in arr)
        }

        logger.info(f"Итоговая агрегация: {total}")
        return True, total
    except Exception as e:
        logger.error(f"Критическая ошибка в get_common_data_aggregated: {str(e)}")
        return False, f"Ошибка обработки данных: {str(e)}"

# ------------------------------
# Получение данных по конверсиям
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
                ] + [("goal_keys[]", key) for key in goal_keys]

                resp = await client.get(
                    f"{BASE_API_URL}/partner/statistic/conversions",
                    headers={"API-KEY": API_KEY},
                    params=params
                )

                if resp.status_code != 200:
                    return False, f"Ошибка /conversions {resp.status_code}: {resp.text}"

                arr = resp.json().get("data", [])
                if not arr:
                    break

                for c in arr:
                    g = c.get("goal", {}).get("key")
                    if g in out:
                        out[g] += 1

                page += 1

        return True, out
    except Exception as e:
        return False, str(e)

# ------------------------------
# Формирование статистики
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
        await query.edit_message_text("Выберите период:", parse_mode="HTML", reply_markup=get_periods_keyboard())
        return

    date_from, date_to, label = await get_dates_for_period(data)
    if date_from and date_to:
        await show_stats_screen(query, context, date_from, date_to, label)

# ------------------------------
# Показ статистики
# ------------------------------
async def show_stats_screen(query, context, date_from: str, date_to: str, label: str):
    okc, cinfo = await get_common_data_aggregated(date_from, date_to)
    if not okc:
        text = f"❗ {cinfo}"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_periods_keyboard())
        return
    cc = cinfo["click_count"]
    uc = cinfo["click_unique"]
    confc = cinfo["conf_count"]
    confp = cinfo["conf_payout"]

    okr, rdata = await get_rfr_aggregated(date_from, date_to)
    if not okr:
        text = f"❗ {rdata}"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=get_periods_keyboard())
        return
    reg = rdata["registration"]
    ftd = rdata["ftd"]
    rd = rdata["rdeposit"]

    date_lbl = f"{date_from[:10]} .. {date_to[:10]}"
    base_text = build_stats_text(label, date_lbl, cc, uc, reg, ftd, rd, confc, confp)

    uniq_id = str(uuid.uuid4())[:8]
    context.user_data.setdefault("stats_store", {})[uniq_id] = {
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

    kb = get_metrics_keyboard(uniq_id)
    await query.edit_message_text(base_text, parse_mode="HTML", reply_markup=kb)

# ------------------------------
# Обработчики
# ------------------------------
telegram_app.add_handler(CommandHandler("start", start_command))
telegram_app.add_handler(CallbackQueryHandler(inline_handler))

# ------------------------------
# Запуск приложения
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    loop = asyncio.get_event_loop()
    loop.create_task(init_telegram_app())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
