import os
import logging
import asyncio
from datetime import datetime, timedelta
import httpx
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
from pydantic import BaseModel, ValidationError  # Добавлен Pydantic

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

# Константы для сообщений
ERROR_UNKNOWN_COMMAND = "Неизвестная команда"
PERIOD_INPUT_INSTRUCTIONS = (
    "🗓 Введите период (YYYY-MM-DD,YYYY-MM-DD)\n"
    "Пример: 2025-02-01,2025-02-10\n"
    "Нажмите 'Назад', чтобы вернуться."
)
BACK_BUTTON_TEXT = "Назад"
MAIN_MENU_TEXT = "Главное меню"

# ------------------------------
# Главное меню (Reply-кнопки)
# ------------------------------
MAIN_MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📊 Получить статистику"), KeyboardButton("ЛК ПП")],
        [KeyboardButton("⬅️ Назад")]
    ],
    resize_keyboard=True,
    one_time_keyboard=False
)

def get_main_menu():
    return MAIN_MENU

# ------------------------------
# Валидация дат через Pydantic
# ------------------------------
class Period(BaseModel):
    start: str
    end: str

# ------------------------------
# Webhook (Telegram + Postback)
# ------------------------------
@app.get("/webhook")
async def verify_webhook():
    return {"status": "ok"}

@app.post("/webhook")
async def webhook_handler(request: Request):
    try:
        data = await request.json()
        if "update_id" in data:
            update = Update.de_json(data, telegram_app.bot)
            await telegram_app.process_update(update)
        else:
            await process_postback_data(data)
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Ошибка вебхука: {e}")
        return {"status": "error"}, 500

# ------------------------------
# Инициализация Telegram
# ------------------------------
async def init_telegram_app():
    if not TELEGRAM_TOKEN:
        logger.critical("TELEGRAM_TOKEN не задан в переменных окружения")
        return
    logger.info("Инициализация Telegram-бота...")
    await telegram_app.initialize()
    await telegram_app.start()
    logger.info("Telegram-бот запущен!")

# ------------------------------
# Удаление сообщения с обработкой ошибок
# ------------------------------
async def try_delete_message(update):
    try:
        await update.message.delete()
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение: {e}")

# ------------------------------
# Postback (конверсия)
# ------------------------------
async def process_postback_data(data: dict):
    logger.debug(f"Postback data: {data}")
    # ... (остаток кода остался без изменений, добавлены логи)
    try:
        await telegram_app.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=msg,
            parse_mode="HTML"
        )
        logger.debug("Postback-сообщение отправлено.")
    except Exception as e:
        logger.exception("Ошибка отправки postback")
        return {"error": "не удалось отправить сообщение"}, 500

# ------------------------------
# /start
# ------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await try_delete_message(update)
    await update.message.reply_text(
        "Привет! Выберите команду:",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )

# ------------------------------
# Агрегация для /common (group_by=day)
# ------------------------------
async def get_common_data_aggregated(date_from: str, date_to: str):
    try:
        logger.info(f"Запрос к /common для периода {date_from} - {date_to}")
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
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
            r.raise_for_status()
    except httpx.HTTPError as e:
        return False, f"HTTP ошибка: {e}"
    data = r.json()
    # ... (остаток кода остался без изменений)

# ------------------------------
# Агрегация для /conversions (registration, ftd, rdeposit)
# ------------------------------
async def get_rfr_aggregated(date_from: str, date_to: str):
    try:
        logger.info(f"Запрос к /conversions для периода {date_from} - {date_to}")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_API_URL}/partner/statistic/conversions",
                headers={"API-KEY": API_KEY},
                params=base_params
            )
            resp.raise_for_status()
    except httpx.HTTPError as e:
        return False, f"HTTP ошибка: {e}"
    # ... (остаток кода остался без изменений)

# ------------------------------
# Формирование метрик через функцию
# ------------------------------
def calculate_metrics(clicks, unique, reg, ftd, rd, payout):
    return {
        "C2R": (reg / clicks * 100) if clicks else 0,
        "R2D": (ftd / reg * 100) if reg else 0,
        "C2D": (ftd / clicks * 100) if clicks else 0,
        "FD2RD": (rd / ftd * 100) if ftd else 0,
        "EPC": (payout / clicks) if clicks else 0,
        "uEPC": (payout / unique) if unique else 0,
    }

def build_metrics(metrics_dict):
    return (
        "🎯 Метрики:\n\n" + 
        "\n".join(f"• {k} = {v:.2f}%" for k, v in metrics_dict.items())
    )

# ------------------------------
# Показ статистики с параллельной агрегацией
# ------------------------------
async def show_stats_screen(query, context, date_from, date_to, label):
    async def fetch_common():
        return await get_common_data_aggregated(date_from, date_to)
    
    async def fetch_rfr():
        return await get_rfr_aggregated(date_from, date_to)
    
    try:
        common_ok, cinfo = await fetch_common()
        rfr_ok, rdata = await fetch_rfr()
    except Exception as e:
        logger.exception("Ошибка агрегации")
        return
    
    if not common_ok or not rfr_ok:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(BACK_BUTTON_TEXT, callback_data="back_periods")]])
        await query.edit_message_text(f"❗ {common_ok or rfr_ok}", reply_markup=kb)
        return
    
    # ... (остаток кода сформированного текста)

# ------------------------------
# Хэндлер ввода дат (Свой период)
# ------------------------------
async def period_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_period"):
        return
    
    await try_delete_message(update)
    
    txt = update.message.text.strip()
    logger.info(f"Ввод периода: {txt}")
    
    if txt.lower() == "назад":
        # ... (логика возврата в меню)
    
    try:
        period = Period(**{k:v.strip() for k,v in zip(["start","end"], txt.split(","))})
    except ValidationError:
        await update.message.reply_text("❗ Неверный формат даты (YYYY-MM-DD).")
        context.user_data["awaiting_period"] = False
        return
    
    st_d = datetime.strptime(period.start, "%Y-%m-%d").date()
    ed_d = datetime.strptime(period.end, "%Y-%m-%d").date()
    
    if st_d > ed_d:
        await update.message.reply_text("❗ Начальная дата больше конечной.")
        return
    
    # ... (остаток кода с обработкой дат)

# ------------------------------
# Управление состоянием через TTL
# ------------------------------
def clean_stats_store(context):
    now = datetime.now()
    to_remove = []
    for key, value in context.user_data.get("stats_store", {}).items():
        if (now - value.get("timestamp", now)).total_seconds() > 3600:
            to_remove.append(key)
    for key in to_remove:
        del context.user_data["stats_store"][key]

# ------------------------------
# Reply-хэндлер для текстовых команд
# ------------------------------
async def reply_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    known_commands = ["📊 Получить статистику", "ЛК ПП", "⬅️ Назад"]
    
    if text not in known_commands:
        return
    
    await try_delete_message(update)
    
    if text == "ЛК ПП":
        link = "Ваш личный кабинет: https://cabinet.4rabetpartner.com/statistics"
        await update.message.reply_text(link, parse_mode="HTML", reply_markup=get_main_menu())
    elif text == "📊 Получить статистику":
        kb = InlineKeyboardMarkup([
            # ... (кнопки выбора периода)
        ])
        await update.message.reply_text("Выберите период:", reply_markup=kb)
    elif text == "⬅️ Назад":
        await update.message.reply_text(MAIN_MENU_TEXT, reply_markup=get_main_menu())

# ------------------------------
# Обновленный inline_handler
# ------------------------------
async def inline_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("update|"):
        clean_stats_store(context)  # Очистка старых данных
    
    # ... (остаток кода с добавленным TTL)

# ------------------------------
# Запуск приложения
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    asyncio.run(init_telegram_app())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
