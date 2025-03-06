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
from pydantic import BaseModel, ValidationError

# Конфигурация
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

# Главное меню (Reply-кнопки)
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

# Валидация дат через Pydantic
class Period(BaseModel):
    start: str
    end: str

# Удаление сообщения с обработкой ошибок
async def try_delete_message(update):
    try:
        await update.message.delete()
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение: {e}")

# Инициализация Telegram
async def init_telegram_app():
    if not TELEGRAM_TOKEN:
        logger.critical("TELEGRAM_TOKEN не задан в переменных окружения")
        return
    logger.info("Инициализация Telegram-бота...")
    await telegram_app.initialize()
    await telegram_app.start()
    logger.info("Telegram-бот запущен!")

# Webhook обработчики
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

# Postback (конверсия)
async def process_postback_data(data: dict):
    logger.debug(f"Postback data: {data}")
    offer_id = data.get("offer_id", "N/A")
    sub_id3 = data.get("sub_id3", "N/A")
    goal = data.get("goal", "N/A")
    revenue = data.get("revenue", "N/A")
    currency = data.get("currency", data.get("currency", "USD"))
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
        logger.exception("Ошибка отправки postback")
        return {"error": "не удалось отправить сообщение"}, 500

# /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await try_delete_message(update)
    await update.message.reply_text(
        "Привет! Выберите команду:",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )

# Агрегация для /common (group_by=day)
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
    arr = data.get("data", [])
    if not arr:
        return True, {
            "click_count": 0,
            "click_unique": 0,
            "conf_count": 0,
            "conf_payout": 0.0
        }
    s_click, s_unique, s_conf, s_pay = 0, 0, 0, 0.0
    for item in arr:
        s_click += item.get("click_count", 0)
        s_unique += item.get("click_unique_count", 0)
        c_ = item.get("conversions", {}).get("confirmed", {})
        s_conf += c_.get("count", 0)
        s_pay += c_.get("payout", 0.0)
    return True, {
        "click_count": s_click,
        "click_unique": s_unique,
        "conf_count": s_conf,
        "conf_payout": s_pay
    }

# Агрегация для /conversions (registration, ftd, rdeposit)
async def get_rfr_aggregated(date_from: str, date_to: str):
    base_params = [
        ("timezone", "Europe/Moscow"),
        ("date_from", date_from),
        ("date_to", date_to),
        ("per_page", "500"),
        ("group_by", "day")
    ]
    for g in ["registration", "ftd", "rdeposit"]:
        base_params.append(("goal_keys[]", g))
    
    try:
        logger.info(f"Запрос к /conversions для периода {date_from} - {date_to}")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_API_URL}/partner/statistic/conversions",
                headers={"API-KEY": API_KEY},
                params=dict(base_params)
            )
            resp.raise_for_status()
    except httpx.HTTPError as e:
        return False, f"HTTP ошибка: {e}"
    data = resp.json()
    arr = data.get("data", [])
    out = {"registration": 0, "ftd": 0, "rdeposit": 0}
    for c in arr:
        g = c.get("goal", {}).get("key")
        if g in out:
            out[g] += 1
    return True, out

# Формирование метрик
def calculate_metrics(clicks, unique, reg, ftd, rd, payout):
    return {
        "C2R": (reg / clicks * 100) if clicks else 0,
        "R2D": (ftd / reg * 100) if reg else 0,
        "C2D": (ftd / clicks * 100) if clicks else 0,
        "FD2RD": (rd / ftd * 100) if ftd else 0,
        "EPC": (payout / clicks) if clicks else 0,
        "uEPC": (payout / unique) if unique else 0,
    }

def build_stats_text(label, date_label, clicks, unique, reg, ftd, rd, conf_count, conf_payout):
    return (
        f"📊 <b>Статистика</b> ({label})\n\n"
        f"🗓 <b>Период:</b> <i>{date_label}</i>\n\n"
        f"👁 <b>Клики:</b> <i>{clicks}</i> (уник: {unique})\n"
        f"🆕 <b>Регистрации:</b> <i>{reg}</i>\n"
        f"💵 <b>FTD:</b> <i>{ftd}</i>\n"
        f"🔄 <b>RD:</b> <i>{rd}</i>\n\n"
        f"✅ <b>Конверсии:</b> <i>{conf_count}</i>\n"
        f"💰 <b>Доход:</b> <i>{conf_payout:.2f} USD</i>\n"
    )

def build_metrics_text(metrics_dict):
    return (
        "🎯 <b>Метрики:</b>\n\n" + 
        "\n".join(f"• <b>{k}</b> = {v:.2f}%" for k, v in metrics_dict.items())
    )

# Показ статистики
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
    
    cc = cinfo["click_count"]
    uc = cinfo["click_unique"]
    confc = cinfo["conf_count"]
    confp = cinfo["conf_payout"]
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
        "confp": confp,
        "timestamp": datetime.now()
    }

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✨ Рассчитать метрики", callback_data=f"metrics|{uniq_id}")],
        [InlineKeyboardButton("Обновить", callback_data=f"update|{uniq_id}")],
        [InlineKeyboardButton("Назад", callback_data="back_periods")]
    ])
    
    await query.edit_message_text(base_text, parse_mode="HTML", reply_markup=kb)

# Хэндлер ввода дат (Свой период)
async def period_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_period"):
        return
    
    await try_delete_message(update)
    
    txt = update.message.text.strip()
    logger.info(f"Ввод периода: {txt}")
    
    if txt.lower() == "назад":
        context.user_data.pop("awaiting_period", None)
        inline_id = context.user_data.pop("inline_msg_id", None)
        if inline_id:
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("Сегодня", callback_data="period_today"),
                    InlineKeyboardButton("7 дней", callback_data="period_7days"),
                    InlineKeyboardButton("За месяц", callback_data="period_month")
                ],
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
        return
    
    try:
        parts = txt.split(",")
        if len(parts) != 2:
            raise ValueError("Неверное количество дат")
        period = Period(start=parts[0].strip(), end=parts[1].strip())
    except (ValidationError, ValueError):
        await update.message.reply_text("❗ Неверный формат даты (YYYY-MM-DD).")
        context.user_data.pop("awaiting_period", None)
        return
    
    try:
        st_d = datetime.strptime(period.start, "%Y-%m-%d").date()
        ed_d = datetime.strptime(period.end, "%Y-%m-%d").date()
    except ValueError:
        await update.message.reply_text("❗ Неверный формат даты.")
        context.user_data.pop("awaiting_period", None)
        return
    
    if st_d > ed_d:
        await update.message.reply_text("❗ Начальная дата больше конечной.")
        context.user_data.pop("awaiting_period", None)
        return
    
    context.user_data.pop("awaiting_period", None)
    inline_id = context.user_data.pop("inline_msg_id", None)
    
    if not inline_id:
        await update.message.reply_text("❗ Не удалось найти сообщение для обновления.")
        return
    
    date_from = f"{st_d} 00:00"
    date_to = f"{ed_d} 23:59"
    lbl = "Свой период"
    chat_id = update.effective_chat.id
    
    try:
        await show_stats_screen(update.callback_query, context, date_from, date_to, lbl)
    except AttributeError:
        fquery = FakeQ(inline_id, chat_id)
        await show_stats_screen(fquery, context, date_from, date_to, lbl)

# Управление состоянием через TTL
def clean_stats_store(context):
    now = datetime.now()
    to_remove = []
    for key, value in context.user_data.get("stats_store", {}).items():
        if (now - value.get("timestamp", now)).total_seconds() > 3600:
            to_remove.append(key)
    for key in to_remove:
        del context.user_data["stats_store"][key]

# Reply-хэндлер для текстовых команд
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
            [
                InlineKeyboardButton("Сегодня", callback_data="period_today"),
                InlineKeyboardButton("7 дней", callback_data="period_7days"),
                InlineKeyboardButton("За месяц", callback_data="period_month")
            ],
            [InlineKeyboardButton("Свой период", callback_data="period_custom")],
            [InlineKeyboardButton("Назад", callback_data="back_menu")]
        ])
        await update.message.reply_text("Выберите период:", reply_markup=kb)
    elif text == "⬅️ Назад":
        await update.message.reply_text(MAIN_MENU_TEXT, reply_markup=get_main_menu())

# Inline-хэндлер для кнопок
async def inline_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "back_menu":
        await query.edit_message_text("Главное меню", parse_mode="HTML")
        await query.message.reply_text("Главное меню:", parse_mode="HTML", reply_markup=get_main_menu())
        return
    
    if data in ["period_today", "period_7days", "period_month"]:
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
        else:
            end_ = datetime.now().date()
            start_ = end_ - timedelta(days=30)
            date_from = f"{start_} 00:00"
            date_to = f"{end_} 23:59"
            label = "Последние 30 дней"
        await show_stats_screen(query, context, date_from, date_to, label)
        return
    
    if data == "period_custom":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(BACK_BUTTON_TEXT, callback_data="back_periods")]])
        await query.edit_message_text(PERIOD_INPUT_INSTRUCTIONS, parse_mode="HTML", reply_markup=kb)
        context.user_data["awaiting_period"] = True
        context.user_data["inline_msg_id"] = query.message.message_id
        return
    
    if data == "back_periods":
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
    
    if data.startswith("metrics|"):
        uniq_id = data.split("|")[1]
        store = context.user_data.get("stats_store", {}).get(uniq_id)
        if not store:
            await query.edit_message_text("❗ Данные не найдены", parse_mode="HTML")
            return
        base_text = store["base_text"]
        metrics = calculate_metrics(
            store["clicks"],
            store["unique"],
            store["reg"],
            store["ftd"],
            store["rd"],
            store["confp"]
        )
        metrics_txt = build_metrics_text(metrics)
        final_txt = base_text + "\n" + metrics_txt
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Скрыть метрики", callback_data=f"hide|{uniq_id}")],
            [InlineKeyboardButton("Обновить", callback_data=f"update|{uniq_id}")],
            [InlineKeyboardButton("Назад", callback_data="back_periods")]
        ])
        await query.edit_message_text(final_txt, parse_mode="HTML", reply_markup=kb)
    
    if data.startswith("hide|"):
        uniq_id = data.split("|")[1]
        store = context.user_data.get("stats_store", {}).get(uniq_id)
        if not store:
            await query.edit_message_text("❗ Данные не найдены", parse_mode="HTML")
            return
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✨ Рассчитать метрики", callback_data=f"metrics|{uniq_id}")],
            [InlineKeyboardButton("Обновить", callback_data=f"update|{uniq_id}")],
            [InlineKeyboardButton("Назад", callback_data="back_periods")]
        ])
        await query.edit_message_text(store["base_text"], parse_mode="HTML", reply_markup=kb)
    
    if data.startswith("update|"):
        clean_stats_store(context)
        uniq_id = data.split("|")[1]
        store = context.user_data.get("stats_store", {}).get(uniq_id)
        if not store:
            await query.edit_message_text("❗ Данные не найдены", parse_mode="HTML")
            return
        await show_stats_screen(
            query,
            context,
            store["date_from"],
            store["date_to"],
            store["label"]
        )

# FakeQ класс для редактирования сообщений
class FakeQ:
    def __init__(self, message_id: int, chat_id: int):
        self.message_id = message_id
        self.chat_id = chat_id
    
    async def edit_message_text(self, text: str, **kwargs):
        await telegram_app.bot.edit_message_text(
            chat_id=self.chat_id,
            message_id=self.message_id,
            text=text,
            **kwargs
        )

# Регистрация хэндлеров
telegram_app.add_handler(CommandHandler("start", start_command))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, period_text_handler), group=1)
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_button_handler), group=2)
telegram_app.add_handler(CallbackQueryHandler(inline_handler))

# Корректный запуск приложения
async def main():
    await init_telegram_app()
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")

if __name__ == "__main__":
    import uvicorn
    asyncio.run(main())
