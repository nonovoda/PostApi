import os
import logging
import asyncio
from datetime import datetime, timedelta
import httpx
import uuid  # Для генерации коротких ID

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

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

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
# Webhook для Telegram и постбеков
# ------------------------------
@app.api_route("/webhook", methods=["GET","POST"])
async def webhook_handler(request: Request):
    if request.method == "GET":
        # postback
        data = dict(request.query_params)
        return await process_postback_data(data)

    # POST
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
    except Exception as e:
        logger.error(f"Ошибка парсинга webhook: {e}")
        return {"status": "ok"}

# ------------------------------
# Инициализация бота
# ------------------------------
async def init_telegram_app():
    logger.info("Инициализация Telegram-бота...")
    await telegram_app.initialize()
    await telegram_app.start()
    logger.info("Telegram-бот запущен!")

# ------------------------------
# Приём постбеков (конверсии)
# ------------------------------
async def process_postback_data(data: dict):
    logger.debug(f"Postback data: {data}")
    offer_id = data.get("offer_id","N/A")
    sub_id2  = data.get("sub_id2","N/A")
    goal     = data.get("goal","N/A")
    revenue  = data.get("revenue","N/A")
    currency = data.get("currency","USD")
    status   = data.get("status","N/A")
    sub_id4  = data.get("sub_id4","N/A")
    sub_id5  = data.get("sub_id5","N/A")
    cdate    = data.get("conversion_date","N/A")

    msg = (
        "🔔 <b>Новая конверсия!</b>\n\n"
        f"<b>📌 Оффер:</b> <i>{offer_id}</i>\n"
        f"<b>🛠 Подход:</b> <i>{sub_id2}</i>\n"
        f"<b>📊 Тип конверсии:</b> <i>{goal}</i>\n"
        f"<b>💰 Выплата:</b> <i>{revenue} {currency}</i>\n"
        f"<b>⚙️ Статус:</b> <i>{status}</i>\n"
        f"<b>🎯 Кампания:</b> <i>{sub_id4}</i>\n"
        f"<b>🎯 Адсет:</b> <i>{sub_id5}</i>\n"
        f"<b>⏰ Время конверсии:</b> <i>{cdate}</i>"
    )
    try:
        await telegram_app.bot.send_message(
            chat_id=os.getenv("TELEGRAM_CHAT_ID","YOUR_CHAT_ID"),
            text=msg,
            parse_mode="HTML",
            reply_markup=get_main_menu()
        )
        logger.debug("Сообщение о постбеке отправлено в Telegram.")
    except Exception as e:
        logger.error(f"Ошибка при отправке постбека: {e}")
        return {"error":"Не отправлено"}, 500

    return {"status":"ok"}

# ------------------------------
# /start
# ------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(1)
    last_id = context.user_data.get("last_msg_id")
    if last_id:
        try:
            await context.bot.delete_message(update.effective_chat.id, last_id)
        except:
            pass

    txt = "Привет! Выберите команду:"
    mk  = get_main_menu()
    sent = await update.message.reply_text(txt, parse_mode="HTML", reply_markup=mk)
    context.user_data["last_msg_id"] = sent.message_id

# ------------------------------
# Запрос /common
# ------------------------------
async def get_common_data(date_from: str, date_to: str):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_API_URL}/partner/statistic/common",
                headers={"API-KEY": API_KEY},
                params={
                    "group_by":"day",
                    "timezone":"Europe/Moscow",
                    "date_from": date_from,
                    "date_to": date_to,
                    "currency_code":"USD"
                }
            )
        if resp.status_code == 200:
            return True, resp.json()
        else:
            return False, f"Ошибка /common: {resp.status_code} {resp.text}"
    except Exception as e:
        return False, f"Ошибка при запросе /common: {e}"

# ------------------------------
# Запрос /conversions (рег, FTD, RD)
# ------------------------------
async def get_rfr(date_from: str, date_to: str):
    """
    registration, ftd, rdeposit
    """
    out = {"registration":0,"ftd":0,"rdeposit":0}
    base_params = [
        ("timezone","Europe/Moscow"),
        ("date_from",date_from),
        ("date_to",date_to),
        ("per_page","500")
    ]
    for g in ["registration","ftd","rdeposit"]:
        base_params.append(("goal_keys[]", g))

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_API_URL}/partner/statistic/conversions",
                headers={"API-KEY": API_KEY},
                params=base_params
            )
        if resp.status_code != 200:
            return False, f"Ошибка /conversions: {resp.status_code} {resp.text}"
        arr = resp.json().get("data",[])
        for c in arr:
            goal_key = c.get("goal",{}).get("key","")
            if goal_key in out:
                out[goal_key]+=1
        return True, out
    except Exception as e:
        return False, f"Ошибка при запросе /conversions: {e}"

# ------------------------------
# Сборка текста без метрик
# ------------------------------
def build_stats_text(label, date_info, clicks, unique_clicks, reg, ftd, rd, conf_count, conf_payout):
    return (
        f"📊 <b>Статистика</b> ({label})\n\n"
        f"🗓 <b>Период:</b> <i>{date_info}</i>\n\n"
        f"👁 <b>Клики:</b> <i>{clicks}</i> (уник: {unique_clicks})\n"
        f"🆕 <b>Регистрации:</b> <i>{reg}</i>\n"
        f"💵 <b>FTD:</b> <i>{ftd}</i>\n"
        f"🔄 <b>RD:</b> <i>{rd}</i>\n\n"
        f"✅ <b>Конверсии:</b> <i>{conf_count}</i>\n"
        f"💰 <b>Доход:</b> <i>{conf_payout} USD</i>\n"
    )

# ------------------------------
# Расчёт метрик
# ------------------------------
def build_metrics_text(clicks, unique_clicks, reg, ftd, rd):
    """
     C2R = (reg/clicks)*100
     R2D = (ftd/reg)*100
     C2D = (ftd/clicks)*100
     EPC = ftd/clicks
     uEPC= ftd/unique_clicks
     Средний чек = (ftd + rd)/ftd
    """
    c2r = (reg/clicks*100) if clicks>0 else 0
    r2d = (ftd/reg*100) if reg>0 else 0
    c2d = (ftd/clicks*100) if clicks>0 else 0
    epc = (ftd/clicks) if clicks>0 else 0
    uepc= (ftd/unique_clicks) if unique_clicks>0 else 0
    avg_check = ((ftd+rd)/ftd) if ftd>0 else 0

    return (
        "🎯 <b>Метрики:</b>\n\n"
        f"• <b>C2R</b> = {c2r:.2f}%\n"
        f"• <b>R2D</b> = {r2d:.2f}%\n"
        f"• <b>C2D</b> = {c2d:.2f}%\n\n"
        f"• <b>EPC</b> = {epc:.3f}\n"
        f"• <b>uEPC</b> = {uepc:.3f}\n\n"
        f"• <b>Средний чек</b> = {avg_check:.2f}\n"
    )

# ------------------------------
# Inline кнопки
# ------------------------------
async def inline_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back_mainmenu":
        # Возвращаемся в главное меню
        await query.edit_message_text("Возвращаюсь в главное меню...", parse_mode="HTML")
        mk = get_main_menu()
        sent = await query.message.reply_text("Главное меню:", parse_mode="HTML", reply_markup=mk)
        context.user_data["last_msg_id"] = sent.message_id
        return

    # Готовые периоды
    if data in ["period_today","period_7days","period_month"]:
        if data == "period_today":
            d_str = datetime.now().strftime("%Y-%m-%d")
            date_from = f"{d_str} 00:00"
            date_to   = f"{d_str} 23:59"
            label = "Сегодня"
        elif data == "period_7days":
            end_d = datetime.now().date()
            start_d = end_d - timedelta(days=6)
            date_from = f"{start_d} 00:00"
            date_to   = f"{end_d} 23:59"
            label = "Последние 7 дней"
        else:
            end_d = datetime.now().date()
            start_d = end_d - timedelta(days=30)
            date_from = f"{start_d} 00:00"
            date_to   = f"{end_d} 23:59"
            label = "Последние 30 дней"

        await show_unified_stats(query, context, date_from, date_to, label)
        return

    if data == "period_custom":
        # Просим ввести даты
        txt = (
            "🗓 <b>Введите период</b> (YYYY-MM-DD,YYYY-MM-DD)\n"
            "Например: 2025-02-01,2025-02-10\n"
            "Напишите 'Назад' для отмены."
        )
        await query.edit_message_text(txt, parse_mode="HTML")
        context.user_data["awaiting_custom_period"] = True
        context.user_data["inline_msg_id"] = query.message.message_id
        return

    # Если нажали "metrics|<id>"
    if data.startswith("metrics|"):
        # Получаем короткий ID
        parts = data.split("|")
        unique_id = parts[1]
        stored = context.user_data.get("stats_storage",{}).get(unique_id)
        if not stored:
            await query.edit_message_text("Данные не найдены, попробуйте снова", parse_mode="HTML")
            return

        # Добавляем метрики
        metxt = build_metrics_text(
            stored["clicks"],
            stored["unique_clicks"],
            stored["registration"],
            stored["ftd"],
            stored["rdeposit"]
        )
        final_msg = stored["base_text"] + "\n" + metxt

        # Кнопка "Скрыть метрики"
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "Скрыть метрики",
                    callback_data=f"hide|{unique_id}"
                )
            ],
            [
                InlineKeyboardButton("Назад", callback_data="back_mainmenu")
            ]
        ])
        await query.edit_message_text(final_msg, parse_mode="HTML", reply_markup=kb)
        return

    # "hide|<id>" - убираем метрики
    if data.startswith("hide|"):
        parts = data.split("|")
        unique_id = parts[1]
        stored = context.user_data.get("stats_storage",{}).get(unique_id)
        if not stored:
            await query.edit_message_text("Данные не найдены", parse_mode="HTML")
            return

        # Возвращаем base_text
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✨ Рассчитать метрики",
                    callback_data=f"metrics|{unique_id}"
                )
            ],
            [
                InlineKeyboardButton("Назад", callback_data="back_mainmenu")
            ]
        ])
        await query.edit_message_text(stored["base_text"], parse_mode="HTML", reply_markup=kb)
        return

    # Иначе
    await query.edit_message_text("Неизвестная команда", parse_mode="HTML")

# ------------------------------
# Отображение объединённых данных + кнопка "✨ Рассчитать метрики"
# ------------------------------
async def show_unified_stats(query, context, date_from: str, date_to: str, label: str):
    # 1) /common
    ok_c, data_c = await get_common_data(date_from, date_to)
    if not ok_c:
        text = f"❗ {data_c}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Назад", callback_data="back_mainmenu")]
        ])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        return

    st = data_c.get("data",[{}])[0]
    gf = st.get("group_fields",[])
    date_info = gf[0].get("label") if gf else "N/A"
    clicks = st.get("click_count",0)
    unique_clicks = st.get("click_unique_count",0)
    c_confirmed = st.get("conversions",{}).get("confirmed",{})
    conf_count  = c_confirmed.get("count",0)
    conf_pay    = c_confirmed.get("payout",0.0)

    # 2) /conversions => registration, ftd, rdeposit
    ok_r, data_r = await get_rfr(date_from, date_to)
    if not ok_r:
        text = f"❗ {data_r}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Назад", callback_data="back_mainmenu")]
        ])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        return

    reg = data_r["registration"]
    ftd = data_r["ftd"]
    rd  = data_r["rdeposit"]

    # Строим основной текст (без метрик)
    base_text = build_stats_text(
        label, date_info, clicks, unique_clicks, reg, ftd, rd, conf_count, conf_pay
    )

    # Сохраняем данные под коротким ID, чтобы избежать длинных callback_data
    unique_id = str(uuid.uuid4())[:8]  # 8 символов
    if "stats_storage" not in context.user_data:
        context.user_data["stats_storage"] = {}
    context.user_data["stats_storage"][unique_id] = {
        "base_text": base_text,
        "clicks": clicks,
        "unique_clicks": unique_clicks,
        "registration": reg,
        "ftd": ftd,
        "rdeposit": rd,
    }

    # inline-кнопка "✨ Рассчитать метрики" => "metrics|<unique_id>"
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✨ Рассчитать метрики",
                callback_data=f"metrics|{unique_id}"
            )
        ],
        [
            InlineKeyboardButton("Назад", callback_data="back_mainmenu")
        ]
    ])
    await query.edit_message_text(base_text, parse_mode="HTML", reply_markup=kb)

# ------------------------------
# Пользователь вводит период вручную
# ------------------------------
async def text_handler_dates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_custom_period"):
        txt = update.message.text.strip()
        if txt.lower() == "назад":
            context.user_data["awaiting_custom_period"] = False
            inline_id = context.user_data.get("inline_msg_id")
            if inline_id:
                kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("Сегодня", callback_data="period_today"),
                        InlineKeyboardButton("7 дней", callback_data="period_7days"),
                        InlineKeyboardButton("За месяц", callback_data="period_month")
                    ],
                    [InlineKeyboardButton("Свой период", callback_data="period_custom")],
                    [InlineKeyboardButton("Назад", callback_data="back_mainmenu")]
                ])
                try:
                    await update.message.delete()
                    await context.bot.edit_message_text(
                        "Выберите период:",
                        parse_mode="HTML",
                        chat_id=update.effective_chat.id,
                        message_id=inline_id,
                        reply_markup=kb
                    )
                except Exception as e:
                    logger.error(f"Ошибка при возврате в меню периодов: {e}")
            return

        # Парсим
        parts = txt.split(",")
        if len(parts)!=2:
            await update.message.delete()
            await context.bot.send_message(
                update.effective_chat.id,
                "❗ Неверный формат (YYYY-MM-DD,YYYY-MM-DD) или 'Назад'"
            )
            return
        try:
            start_d = datetime.strptime(parts[0].strip(),"%Y-%m-%d").date()
            end_d   = datetime.strptime(parts[1].strip(),"%Y-%m-%d").date()
        except:
            await update.message.delete()
            await context.bot.send_message(
                update.effective_chat.id,
                "❗ Ошибка разбора дат. Повторите или 'Назад'."
            )
            return

        if start_d > end_d:
            await update.message.delete()
            await context.bot.send_message(
                update.effective_chat.id,
                "❗ Начальная дата больше конечной!"
            )
            return

        context.user_data["awaiting_custom_period"] = False
        inline_id = context.user_data["inline_msg_id"]
        await update.message.delete()

        date_from = f"{start_d} 00:00"
        date_to   = f"{end_d} 23:59"
        label     = f"{start_d} - {end_d}"

        # "Фейковый query", чтобы вызвать show_unified_stats
        class FakeQuery:
            def __init__(self, msg_id, chat_id):
                self.message = type("Msg", (), {})()
                self.message.message_id = msg_id
                self.message.chat_id    = chat_id
            async def edit_message_text(self,*args,**kwargs):
                return await context.bot.edit_message_text(
                    chat_id=self.message.chat_id,
                    message_id=self.message.message_id,
                    *args,**kwargs
                )
            async def answer(self):
                pass

        fake_query = FakeQuery(inline_id, update.effective_chat.id)
        await show_unified_stats(fake_query, context, date_from, date_to, label)

# ------------------------------
# Обработка Reply-кнопок (ЛК ПП, Получить статистику)
# ------------------------------
async def reply_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(1)
    try:
        await update.message.delete()
    except:
        pass

    await asyncio.sleep(1)
    last_id = context.user_data.get("last_msg_id")
    if last_id:
        try:
            await context.bot.delete_message(update.effective_chat.id, last_id)
        except:
            pass

    text = update.message.text.strip()

    if text == "ЛК ПП":
        link_text = "Ваш личный кабинет партнёра: https://cabinet.4rabetpartner.com/statistics"
        sent = await update.message.reply_text(link_text, parse_mode="HTML", reply_markup=get_main_menu())
        context.user_data["last_msg_id"] = sent.message_id
        return

    if text == "📊 Получить статистику":
        # Отправляем inline-кнопки: period_today, period_7days, period_month, period_custom
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

    # Иначе
    msg = await update.message.reply_text("Неизвестная команда", parse_mode="HTML", reply_markup=get_main_menu())
    context.user_data["last_msg_id"] = msg.message_id

# ------------------------------
# Регистрация хэндлеров
# ------------------------------
telegram_app.add_handler(CommandHandler("start", start_command))
# Сначала проверяем ввод дат (group=1)
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler_dates), group=1)
# Потом обрабатываем остальные Reply-кнопки (group=2)
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_button_handler), group=2)
# Inline-кнопки (show stats, metrics)
telegram_app.add_handler(CallbackQueryHandler(inline_button_handler))

# ------------------------------
# Запуск приложения
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    loop = asyncio.get_event_loop()
    loop.create_task(init_telegram_app())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
