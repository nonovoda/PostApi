import os
import logging
import asyncio
from datetime import datetime, timedelta
import httpx
import uuid  # Для коротких ID в callback_data
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
API_KEY = os.getenv("PP_API_KEY","ВАШ_API_КЛЮЧ")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN","ВАШ_ТОКЕН")
BASE_API_URL = "https://4rabet.api.alanbase.com/v1"
PORT = int(os.environ.get("PORT",8000))

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

# ------------------------------
# Главное меню (Reply-кнопки)
# ------------------------------
def get_main_menu():
    """
    Кнопки: Получить статистику, ЛК ПП, Назад
    """
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
@app.api_route("/webhook", methods=["GET","POST"])
async def webhook_handler(request: Request):
    if request.method=="GET":
        # postback
        data = dict(request.query_params)
        return await process_postback_data(data)
    # POST
    try:
        data = await request.json()
        if "update_id" in data:
            update = Update.de_json(data, telegram_app.bot)
            if not telegram_app.running:
                await init_telegram_app()
            await telegram_app.process_update(update)
            return {"status":"ok"}
        else:
            # postback
            return await process_postback_data(data)
    except Exception as e:
        logger.error(f"Ошибка разбора webhook: {e}")
        return {"status":"ok"}

# ------------------------------
# Инициализация бота
# ------------------------------
async def init_telegram_app():
    logger.info("Инициализация Telegram-бота...")
    await telegram_app.initialize()
    await telegram_app.start()
    logger.info("Telegram-бот запущен!")

# ------------------------------
# Обработка postback
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
        logger.debug("Postback-сообщение отправлено в Telegram.")
    except Exception as e:
        logger.error(f"Ошибка postback: {e}")
        return {"error":"Не удалось отправить"}, 500

    return {"status":"ok"}

# ------------------------------
# /start
# ------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(1)
    last = context.user_data.get("last_msg_id")
    if last:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last)
        except:
            pass

    txt = "Привет! Выберите команду:"
    mk  = get_main_menu()
    sent = await update.message.reply_text(txt, parse_mode="HTML", reply_markup=mk)
    context.user_data["last_msg_id"] = sent.message_id

# --------------------------------------------------------
# (2), (3), (4): Исправляем логику, чтобы суммировать дни
# --------------------------------------------------------
async def get_common_data_aggregated(date_from: str, date_to: str):
    """
    Запрос /partner/statistic/common c group_by=day,
    затем суммируем клики, уник.клики, confirmed.
    Возвращаем (ok, {click_count, click_unique_count, conf_count, conf_payout, date_label})
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
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
        if r.status_code!=200:
            return False, f"Ошибка /common {r.status_code}: {r.text}"

        data = r.json()
        arr = data.get("data", [])
        if not arr:
            # Если пусто, вернём 0
            return True, {
                "click_count":0,
                "click_unique":0,
                "conf_count":0,
                "conf_payout":0.0,
                "date_label":"N/A"
            }

        sum_click, sum_unique, sum_conf, sum_pay = 0,0,0,0.0
        # date_label формируем как "X - Y" (например, "2025-02-20 - 2025-02-26")
        # Или берём group_fields[0]["label"] c первого+последнего? Для упрощения:
        # Просто вернём f"{date_from}..{date_to}"?
        # Но user wants short label => We'll do it outside
        for item in arr:
            sum_click += item.get("click_count",0)
            sum_unique += item.get("click_unique_count",0)
            c_ = item.get("conversions",{}).get("confirmed",{})
            sum_conf += c_.get("count",0)
            sum_pay  += c_.get("payout",0.0)

        return True, {
            "click_count": sum_click,
            "click_unique": sum_unique,
            "conf_count": sum_conf,
            "conf_payout": sum_pay,
            # date_label user sees from label or from period name
            "date_label": ""  # заполним позже
        }
    except Exception as e:
        return False, str(e)

# Запрашиваем /partner/statistic/conversions (registration, ftd, rdeposit)
async def get_rfr_aggregated(date_from: str, date_to: str):
    """
    Аналогично суммируем day-by-day. group_by=day. 
    """
    out = {"registration":0,"ftd":0,"rdeposit":0}
    base_params = {
        "timezone": "Europe/Moscow",
        "date_from": date_from,
        "date_to": date_to,
        "per_page": "500",
        "group_by": "day"
    }
    # Параметры goal_keys[] = registration, ftd, rdeposit
    # httpx.Params(...) + repeated? We'll do it in a simpler approach:
    # We'll do multiple requests or sum? Actually, we can do one request with repeated param:
    # "goal_keys[]=registration", "goal_keys[]=ftd", "goal_keys[]=rdeposit"
    # Then we'll sum day by day.

    # We'll do the day approach:
    # In code we do:
    client_params = []
    for k,v in base_params.items():
        client_params.append((k,v))
    for g in ["registration","ftd","rdeposit"]:
        client_params.append(("goal_keys[]", g))

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            rr = await client.get(
                f"{BASE_API_URL}/partner/statistic/conversions",
                headers={"API-KEY": API_KEY},
                params=client_params
            )
        if rr.status_code!=200:
            return False, f"Ошибка /conversions {rr.status_code}: {rr.text}"
        data = rr.json()
        arr = data.get("data",[])
        if not arr:
            return True, out  # всё 0

        # Каждый item - 1 day
        for item in arr:
            g = item.get("goal",{}).get("key")
            if g in out:
                out[g]+=1

        return True, out
    except Exception as e:
        return False, str(e)

# ------------------------------
# Формируем текст без метрик
# ------------------------------
def build_stats_text(
    label: str,
    date_label: str,
    clicks: int, unique_clicks: int,
    reg_count: int, ftd_count: int, rd_count: int,
    conf_count: int, conf_payout: float
) -> str:
    """
    (1) Single message with:
    Статистика (Label)
    Период: date_label

    Клики, Рег, FTD, RD, Конверсии, Доход

    (6) - средний чек УДАЛЁН
    """
    text = (
        f"📊 <b>Статистика</b> ({label})\n\n"
        f"🗓 <b>Период:</b> <i>{date_label}</i>\n\n"
        f"👁 <b>Клики:</b> <i>{clicks}</i> (уник: {unique_clicks})\n"
        f"🆕 <b>Регистрации:</b> <i>{reg_count}</i>\n"
        f"💵 <b>FTD:</b> <i>{ftd_count}</i>\n"
        f"🔄 <b>RD:</b> <i>{rd_count}</i>\n\n"
        f"✅ <b>Конверсии:</b> <i>{conf_count}</i>\n"
        f"💰 <b>Доход:</b> <i>{conf_payout:.2f} USD</i>\n"
    )
    return text

# ------------------------------
# Метрики (убираем средний чек #6)
# ------------------------------
def build_metrics(
    clicks: int, unique_clicks: int,
    reg_count: int, ftd_count: int
    # no rd_count needed for average check, because #6 - remove
) -> str:
    """
    • C2R = reg/clicks * 100%
    • R2D = ftd/reg * 100%
    • C2D = ftd/clicks * 100%
    • EPC = ftd/clicks
    • uEPC= ftd/unique_clicks
    (no average check)
    """
    c2r = (reg_count/clicks*100) if clicks>0 else 0
    r2d = (ftd_count/reg_count*100) if reg_count>0 else 0
    c2d = (ftd_count/clicks*100) if clicks>0 else 0
    epc = (ftd_count/clicks) if clicks>0 else 0
    uepc= (ftd_count/unique_clicks) if unique_clicks>0 else 0
    text = (
        "🎯 <b>Метрики:</b>\n\n"
        f"• <b>C2R</b> = {c2r:.2f}%\n"
        f"• <b>R2D</b> = {r2d:.2f}%\n"
        f"• <b>C2D</b> = {c2d:.2f}%\n\n"
        f"• <b>EPC</b> = {epc:.3f}\n"
        f"• <b>uEPC</b> = {uepc:.3f}\n"
    )
    return text

# ------------------------------
# Inline-кнопки (1 уровень: выбор периода, 2 уровень: статистика)
# ------------------------------
async def inline_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cbdata = query.data

    # Уровень 1: Выбор периода
    if cbdata=="back_menu":
        # Возвращаемся в главное меню
        await query.edit_message_text("Главное меню", parse_mode="HTML")
        mk = get_main_menu()
        sent = await query.message.reply_text("Главное меню:", parse_mode="HTML", reply_markup=mk)
        context.user_data["last_msg_id"] = sent.message_id
        return

    if cbdata in ["period_today","period_7days","period_month"]:
        # Получаем date_from / date_to
        if cbdata=="period_today":
            day_str = datetime.now().strftime("%Y-%m-%d")
            date_from = f"{day_str} 00:00"
            date_to   = f"{day_str} 23:59"
            period_label = "Сегодня"
        elif cbdata=="period_7days":
            end_ = datetime.now().date()
            start_ = end_ - timedelta(days=6)
            date_from = f"{start_} 00:00"
            date_to   = f"{end_} 23:59"
            period_label = "Последние 7 дней"
        else:  # month
            end_ = datetime.now().date()
            start_ = end_ - timedelta(days=30)
            date_from = f"{start_} 00:00"
            date_to   = f"{end_} 23:59"
            period_label = "Последние 30 дней"

        await show_stats_screen(query, context, date_from, date_to, period_label)
        return

    if cbdata=="period_custom":
        # Просим ввод дат
        txt = (
            "🗓 Введите период (YYYY-MM-DD,YYYY-MM-DD)\n"
            "Пример: 2025-02-01,2025-02-10\n"
            "Напишите 'Назад' для отмены"
        )
        await query.edit_message_text(txt, parse_mode="HTML")
        context.user_data["awaiting_period"] = True
        context.user_data["inline_msg_id"] = query.message.message_id
        return

    # (5) "Назад" = Возврат на предыдущий шаг
    # У нас:
    #  - "Назад" из статистики => вернуть к выбору периода
    #  - "Назад" из периодов => вернуть в главное меню
    # Но мы сделали 2 "back":
    #   "back_periods" => вернуться к периодам
    #   "back_menu" => вернуться к главному меню
    if cbdata=="back_periods":
        # Вернём меню периодов
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Сегодня", callback_data="period_today"),
                InlineKeyboardButton("7 дней", callback_data="period_7days"),
                InlineKeyboardButton("За месяц", callback_data="period_month")
            ],
            [
                InlineKeyboardButton("Свой период", callback_data="period_custom")
            ],
            [
                InlineKeyboardButton("Назад", callback_data="back_menu")
            ]
        ])
        await query.edit_message_text("Выберите период:", parse_mode="HTML", reply_markup=kb)
        return

    # Если нажали «Рассчитать метрики» -> "stats_metrics|uniqueid"
    if cbdata.startswith("stats_metrics|"):
        unique_id = cbdata.split("|")[1]
        store = context.user_data.get("stats_store",{}).get(unique_id)
        if not store:
            await query.edit_message_text("❗ Данные не найдены", parse_mode="HTML")
            return
        # добавим метрики
        text_base = store["base_text"]
        # метрики
        clicks = store["clicks"]
        uniq   = store["unique"]
        reg_   = store["reg"]
        ftd_   = store["ftd"]
        rd_    = store["rd"]

        metrics = build_metrics(clicks, uniq, reg_, ftd_)
        final_text = text_base + "\n" + metrics
        # Кнопка "Скрыть метрики" => stats_hide|uniqueid
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Скрыть метрики", callback_data=f"stats_hide|{unique_id}")
            ],
            [
                InlineKeyboardButton("Назад", callback_data="back_periods")
            ]
        ])
        await query.edit_message_text(final_text, parse_mode="HTML", reply_markup=kb)
        return

    # "stats_hide|uniqueid" => убрать метрики, показать base_text
    if cbdata.startswith("stats_hide|"):
        uniqid = cbdata.split("|")[1]
        store = context.user_data.get("stats_store",{}).get(uniqid)
        if not store:
            await query.edit_message_text("Данные не найдены", parse_mode="HTML")
            return
        base_ = store["base_text"]
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✨ Рассчитать метрики", callback_data=f"stats_metrics|{uniqid}")
            ],
            [
                InlineKeyboardButton("Назад", callback_data="back_periods")
            ]
        ])
        await query.edit_message_text(base_ , parse_mode="HTML", reply_markup=kb)
        return

    # Неизвестный
    await query.edit_message_text("Неизвестная команда", parse_mode="HTML")

# ------------------------------
# Показ итоговой статистики
# ------------------------------
async def show_stats_screen(query, context, date_from: str, date_to: str, label: str):
    # 1) /common => sum days
    okc, cdata = await get_common_data_aggregated(date_from, date_to)
    if not okc:
        text = f"❗ {cdata}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_periods")]])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        return

    # cdata = {click_count, click_unique, conf_count, conf_payout, date_label=...}
    sum_clicks  = cdata["click_count"]
    sum_uniques = cdata["click_unique"]
    sum_conf    = cdata["conf_count"]
    sum_pay     = cdata["conf_payout"]
    # date_label => хотим показать (date_from .. date_to)?
    # Для наглядности:
    date_label = f"{date_from[:10]} .. {date_to[:10]}"

    # 2) /conversions => registration, ftd, rdeposit
    okr, rdata = await get_rfr_aggregated(date_from, date_to)
    if not okr:
        text = f"❗ {rdata}"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_periods")]])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        return

    reg = rdata["registration"]
    ftd = rdata["ftd"]
    rd  = rdata["rdeposit"]

    # Формируем единое сообщение
    base_text = build_stats_text(
        label=label,
        date_label=date_label,
        clicks=sum_clicks,
        unique_clicks=sum_uniques,
        reg_count=reg,
        ftd_count=ftd,
        rd_count=rd,
        conf_count=sum_conf,
        conf_payout=sum_pay
    )

    # Сохраняем в user_data
    if "stats_store" not in context.user_data:
        context.user_data["stats_store"] = {}
    unique_id = str(uuid.uuid4())[:8]
    context.user_data["stats_store"][unique_id] = {
        "base_text": base_text,
        "clicks": sum_clicks,
        "unique": sum_uniques,
        "reg": reg,
        "ftd": ftd,
        "rd": rd
    }

    # Кнопка "Рассчитать метрики" => stats_metrics|unique_id
    # Кнопка "Назад" => back_periods (вернём в меню периодов)
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✨ Рассчитать метрики", callback_data=f"stats_metrics|{unique_id}")
        ],
        [
            InlineKeyboardButton("Назад", callback_data="back_periods")
        ]
    ])
    await query.edit_message_text(base_text, parse_mode="HTML", reply_markup=kb)

# ------------------------------
# Пользователь вводит период вручную
# ------------------------------
async def text_handler_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_period"):
        txt = update.message.text.strip()
        if txt.lower()=="назад":
            context.user_data["awaiting_period"]=False
            inline_id = context.user_data.get("inline_msg_id")
            if inline_id:
                # Вернём меню периодов
                kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("Сегодня", callback_data="period_today"),
                        InlineKeyboardButton("7 дней", callback_data="period_7days"),
                        InlineKeyboardButton("За месяц", callback_data="period_month")
                    ],
                    [
                        InlineKeyboardButton("Свой период", callback_data="period_custom")
                    ],
                    [
                        InlineKeyboardButton("Назад", callback_data="back_menu")
                    ]
                ])
                await update.message.delete()
                try:
                    await context.bot.edit_message_text(
                        text="Выберите период:",
                        chat_id=update.effective_chat.id,
                        message_id=inline_id,
                        parse_mode="HTML",
                        reply_markup=kb
                    )
                except Exception as e:
                    logger.error(f"Ошибка возврата в меню периодов: {e}")
            return

        # Парсим
        parts = txt.split(",")
        if len(parts)!=2:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❗ Формат: YYYY-MM-DD,YYYY-MM-DD или 'Назад'"
            )
            return
        try:
            start_d = datetime.strptime(parts[0].strip(),"%Y-%m-%d").date()
            end_d   = datetime.strptime(parts[1].strip(),"%Y-%m-%d").date()
        except:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❗ Ошибка парсинга дат"
            )
            return
        if start_d > end_d:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❗ Начальная дата больше конечной!"
            )
            return

        context.user_data["awaiting_period"]=False
        inline_id = context.user_data["inline_msg_id"]
        await update.message.delete()

        date_from = f"{start_d} 00:00"
        date_to   = f"{end_d} 23:59"
        lbl       = f"Свой период"

        # Создаём фейковый query, чтобы вызвать show_stats_screen
        class FakeQuery:
            def __init__(self, msg_id, c_id):
                self.message = type("Msg",(),{})()
                self.message.message_id = msg_id
                self.message.chat_id = c_id
            async def edit_message_text(self,*args,**kwargs):
                return await context.bot.edit_message_text(
                    chat_id=self.message.chat_id,
                    message_id=self.message.message_id,
                    *args,**kwargs
                )
            async def answer(self):
                pass
        fquery = FakeQuery(inline_id, update.effective_chat.id)
        await show_stats_screen(fquery, context, date_from, date_to, lbl)

# ------------------------------
# Обработка Reply-кнопок
# ------------------------------
async def reply_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(1)
    try:
        await update.message.delete()
    except:
        pass
    await asyncio.sleep(1)
    last = context.user_data.get("last_msg_id")
    if last:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last)
        except:
            pass

    text = update.message.text.strip()
    if text=="ЛК ПП":
        link = "Ваш личный кабинет: https://cabinet.4rabetpartner.com/statistics"
        sent = await update.message.reply_text(link, parse_mode="HTML", reply_markup=get_main_menu())
        context.user_data["last_msg_id"] = sent.message_id
        return
    if text=="📊 Получить статистику":
        # Показываем меню периодов
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Сегодня", callback_data="period_today"),
                InlineKeyboardButton("7 дней", callback_data="period_7days"),
                InlineKeyboardButton("За месяц", callback_data="period_month")
            ],
            [
                InlineKeyboardButton("Свой период", callback_data="period_custom")
            ],
            [
                InlineKeyboardButton("Назад", callback_data="back_menu")
            ]
        ])
        sent = await update.message.reply_text("Выберите период:", parse_mode="HTML", reply_markup=kb)
        context.user_data["last_msg_id"] = sent.message_id
        return
    if text=="⬅️ Назад":
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
# (4) "Свой период" => text_handler_period
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler_period), group=1)
# Reply-кнопки
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_button_handler), group=2)
# Inline
telegram_app.add_handler(CallbackQueryHandler(inline_handler))

# ------------------------------
# Запуск
# ------------------------------
if __name__=="__main__":
    import uvicorn
    loop = asyncio.get_event_loop()
    loop.create_task(init_telegram_app())
    uvicorn.run(app, host="0.0.0.0", port=PORT)

