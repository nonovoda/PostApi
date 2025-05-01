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

# ------------------------------
# Конфигурация
# ------------------------------
API_KEY = os.getenv("PP_API_KEY", "ВАШ_API_КЛЮЧ")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН")
BASE_API_URL = "https://4rabet.api.alanbase.com/v1"
PORT = int(os.environ.get("PORT", 8000))
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID")  # 🔒 Должен быть числовой ID

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
        # Приводим оба значения к целым числам
        current_chat_id = int(update.effective_chat.id)
        allowed_chat_id = int(TELEGRAM_CHAT_ID.strip())
        
        logger.debug(f"Проверка доступа: {current_chat_id} vs {allowed_chat_id}")
        
        if current_chat_id != allowed_chat_id:
            logger.warning(f"🚨 Доступ запрещён для: {current_chat_id}")
            # Удаляем сообщение и уведомляем пользователя
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

# ------------------------------
# Агрегация для /common (group_by=day)
# ------------------------------
async def get_common_data_aggregated(date_from: str, date_to: str):
    try:
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
        if r.status_code != 200:
            return False, f"Ошибка /common {r.status_code}: {r.text}"
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
    except Exception as e:
        return False, f"Ошибка /common: {str(e)}"

# ------------------------------
# Агрегация для /conversions (registration, ftd, rdeposit)
# ------------------------------
async def get_rfr_aggregated(date_from: str, date_to: str):
    out = {"registration": 0, "ftd": 0, "rdeposit": 0}
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
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{BASE_API_URL}/partner/statistic/conversions",
                headers={"API-KEY": API_KEY},
                params=base_params
            )
        if resp.status_code != 200:
            return False, f"Ошибка /conversions {resp.status_code}: {resp.text}"
        arr = resp.json().get("data", [])
        for c in arr:
            g = c.get("goal", {}).get("key")
            if g in out:
                out[g] += 1
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
    # 🔒 Проверка доступа
    if not await check_access(update):
        return

    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back_menu":
        await query.edit_message_text("Главное меню", parse_mode="HTML")
        mk = get_main_menu()
        await query.message.reply_text("Главное меню:", parse_mode="HTML", reply_markup=mk)
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
        return

    if data.startswith("metrics|"):
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

    if data.startswith("hide|"):
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

    if data.startswith("update|"):
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
# Регистрация хэндлеров
# ------------------------------
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
