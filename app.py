import os
import logging
import asyncio
from datetime import datetime, timedelta
import httpx

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
# Универсальный webhook: Telegram / postback
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
# Обработка POSTBACK (конверсия)
# ------------------------------
async def process_postback_data(data: dict):
    logger.debug(f"Postback data: {data}")

    offer_id = data.get("offer_id", "N/A")
    sub_id2 = data.get("sub_id2", "N/A")
    goal = data.get("goal", "N/A")
    revenue = data.get("revenue", "N/A")
    currency = data.get("currency", "USD")
    status = data.get("status", "N/A")
    sub_id4 = data.get("sub_id4", "N/A")
    sub_id5 = data.get("sub_id5", "N/A")
    conversion_date = data.get("conversion_date", "N/A")

    msg = (
        "🔔 <b>Новая конверсия!</b>\n\n"
        f"<b>📌 Оффер:</b> <i>{offer_id}</i>\n"
        f"<b>🛠 Подход:</b> <i>{sub_id2}</i>\n"
        f"<b>📊 Тип конверсии:</b> <i>{goal}</i>\n"
        f"<b>💰 Выплата:</b> <i>{revenue} {currency}</i>\n"
        f"<b>⚙️ Статус:</b> <i>{status}</i>\n"
        f"<b>🎯 Кампания:</b> <i>{sub_id4}</i>\n"
        f"<b>🎯 Адсет:</b> <i>{sub_id5}</i>\n"
        f"<b>⏰ Время конверсии:</b> <i>{conversion_date}</i>"
    )

    try:
        await telegram_app.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=msg,
            parse_mode="HTML",
            reply_markup=get_main_menu()
        )
        logger.debug("Сообщение о постбеке отправлено в Telegram.")
    except Exception as e:
        logger.error(f"Ошибка при отправке постбека: {e}")
        return {"error": "Не удалось отправить сообщение"}, 500

    return {"status": "ok"}

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

    text = "Привет! Выберите команду:"
    mk = get_main_menu()
    sent = await update.message.reply_text(text, parse_mode="HTML", reply_markup=mk)
    context.user_data["last_msg_id"] = sent.message_id

# ------------------------------
# Запрос /common
# ------------------------------
async def get_common_data(date_from: str, date_to: str):
    """
    Делаем запрос /common, возвращаем (ok, data|error)
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
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
        if resp.status_code == 200:
            return True, resp.json()
        else:
            return False, f"Ошибка /common: {resp.status_code} {resp.text}"
    except Exception as e:
        return False, f"Ошибка запроса /common: {e}"

# ------------------------------
# Запрос /conversions для 3 ключей (registration, ftd, rdeposit)
# ------------------------------
async def get_reg_ftd_rd(date_from: str, date_to: str):
    """
    Вернём словарь: {
      "registration": <count>,
      "ftd": <count>,
      "rdeposit": <count>
    }
    """
    base_params = [
        ("timezone", "Europe/Moscow"),
        ("date_from", date_from),
        ("date_to", date_to),
        ("per_page", "500"),
    ]
    # Для bet? Вы не упомянули bet в финальном сообщении, поэтому не считаем.
    for g in ["registration", "ftd", "rdeposit"]:
        base_params.append(("goal_keys[]", g))

    out = {"registration":0, "ftd":0, "rdeposit":0}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_API_URL}/partner/statistic/conversions",
                headers={"API-KEY": API_KEY},
                params=base_params
            )
        if resp.status_code != 200:
            return False, f"Ошибка /conversions: {resp.status_code} {resp.text}"
        arr = resp.json().get("data", [])
        for c in arr:
            goal_key = c.get("goal",{}).get("key","")
            if goal_key in out:
                out[goal_key]+=1
        return True, out
    except Exception as e:
        return False, str(e)

# ------------------------------
# Формируем итоговое сообщение
# ------------------------------
def build_final_message(
    period_label: str,
    date_info: str,
    clicks: int,
    unique_clicks: int,
    reg_count: int,
    ftd_count: int,
    rd_count: int,
    conf_count: int,
    conf_payout: float,
    metrics_text: str = ""
) -> str:
    """
    Собираем всё в одно сообщение (без метрик).
    При желании можно добавить metrics_text внизу.
    """
    msg = (
        f"📊 <b>Статистика</b> ({period_label})\n\n"
        f"🗓 <b>Период:</b> <i>{date_info}</i>\n\n"
        f"👁 <b>Клики:</b> <i>{clicks}</i> (уник: {unique_clicks})\n"
        f"🆕 <b>Регистрации:</b> <i>{reg_count}</i>\n"
        f"💵 <b>FTD:</b> <i>{ftd_count}</i>\n"
        f"🔄 <b>RD:</b> <i>{rd_count}</i>\n\n"
        f"✅ <b>Конверсии:</b> <i>{conf_count}</i>\n"
        f"💰 <b>Доход:</b> <i>{conf_payout} USD</i>\n"
    )
    if metrics_text:
        # Добавим блок метрик в конце
        msg += f"\n{metrics_text}\n"
    return msg

def build_metrics_text(
    clicks: int,
    unique_clicks: int,
    reg_count: int,
    ftd_count: int,
    rd_count: int
) -> str:
    """
    Метрики:
     C2R = (рег / клики)*100%
     R2D = (ftd / рег)*100%
     C2D = (ftd / клики)*100%
     EPC = ftd / клики
     uEPC = ftd / уник. клики
     Средний чек = (ftd + rd) / ftd
    """
    # Защита от деления на ноль
    c2r = (reg_count/clicks*100) if clicks>0 else 0
    r2d = (ftd_count/reg_count*100) if reg_count>0 else 0
    c2d = (ftd_count/clicks*100) if clicks>0 else 0
    epc = ftd_count/clicks if clicks>0 else 0
    uepc = ftd_count/unique_clicks if unique_clicks>0 else 0

    # Средний чек (предположим, речь о кол-ве, раз уж FTD + RD — count):
    avg_check = (ftd_count + rd_count)/ftd_count if ftd_count>0 else 0

    # Оформим красиво, добавим эмодзи
    text = (
        "🎯 <b>Метрики:</b>\n\n"
        f"• <b>C2R</b> = {c2r:.2f}%\n"
        f"• <b>R2D</b> = {r2d:.2f}%\n"
        f"• <b>C2D</b> = {c2d:.2f}%\n\n"
        f"• <b>EPC</b> = {epc:.3f}\n"
        f"• <b>uEPC</b> = {uepc:.3f}\n\n"
        f"• <b>Средний чек</b> = {avg_check:.2f}\n"
    )
    return text

# ------------------------------
# При нажатии inline-кнопок
# ------------------------------
async def inline_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # Кнопка "Назад" в главное меню
    if data == "back_mainmenu":
        # Убираем inline-кнопки, пишем "Главное меню"
        await query.edit_message_text("Возвращаюсь в главное меню...", parse_mode="HTML")
        # Показываем главное меню
        mk = get_main_menu()
        sent = await query.message.reply_text("Главное меню:", parse_mode="HTML", reply_markup=mk)
        context.user_data["last_msg_id"] = sent.message_id
        return

    # -------------- Готовые периоды --------------
    if data in ["period_today","period_7days","period_month"]:
        # Определим date_from/date_to
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
        else: # period_month
            end_d = datetime.now().date()
            start_d = end_d - timedelta(days=30)
            date_from = f"{start_d} 00:00"
            date_to   = f"{end_d} 23:59"
            label = "Последние 30 дней"

        await show_stats_unified(query, context, date_from, date_to, label)
        return

    # -------------- Свой период --------------
    if data == "period_custom":
        # Просим ввести даты
        txt = (
            "🗓 <b>Введите период</b> в формате <code>YYYY-MM-DD,YYYY-MM-DD</code>.\n"
            "Например: 2025-02-01,2025-02-10\n"
            "Напишите 'Назад' для отмены."
        )
        await query.edit_message_text(txt, parse_mode="HTML")
        context.user_data["awaiting_custom_period"] = True
        context.user_data["inline_msg_id"] = query.message.message_id
        return

    # -------------- Рассчитать метрики --------------
    if data.startswith("metrics|"):
        # data: "metrics|date_from|date_to|label|reg|ftd|rd|clicks|unique"
        parts = data.split("|")
        date_from = parts[1]
        date_to   = parts[2]
        label     = parts[3]
        reg_count = int(parts[4])
        ftd_count = int(parts[5])
        rd_count  = int(parts[6])
        clicks    = int(parts[7])
        unique_clicks = int(parts[8])

        # Строим метрики
        metrics_str = build_metrics_text(
            clicks, unique_clicks, reg_count, ftd_count, rd_count
        )

        # Нужно дополнить текущее сообщение (у нас уже есть info).
        # Сохранили info при show_stats_unified -> context.user_data?
        # Но проще: context.user_data["stats_msg"]. Либо —
        # Можно было всё сгенерировать заново. Но удобнее хранить, как last version.

        stored_msg = context.user_data.get("last_stats_msg", "")  # уже готовый текст без метрик
        final_msg = stored_msg + f"\n{metrics_str}"

        # Кнопка "Назад" => show_stats_unified (без метрик)
        # callback_data="back_nometric|..."
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "Скрыть метрики",
                    callback_data=f"back_nometric|{date_from}|{date_to}|{label}|{reg_count}|{ftd_count}|{rd_count}|{clicks}|{unique_clicks}"
                )
            ],
            [
                InlineKeyboardButton("Назад", callback_data="back_mainmenu")
            ]
        ])

        await query.edit_message_text(final_msg, parse_mode="HTML", reply_markup=kb)
        return

    # -------------- Скрыть метрики --------------
    if data.startswith("back_nometric|"):
        # back_nometric|date_from|date_to|label|reg|ftd|rd|clicks|unique
        parts = data.split("|")
        date_from = parts[1]
        date_to   = parts[2]
        label     = parts[3]
        reg_count = int(parts[4])
        ftd_count = int(parts[5])
        rd_count  = int(parts[6])
        clicks    = int(parts[7])
        unique_clicks = int(parts[8])

        # Снова строим сообщение без метрик
        # Но context.user_data["last_stats_msg"] уже содержит его
        msg_nometric = context.user_data.get("last_stats_msg", "Нет данных")

        # Кнопка "Рассчитать метрики"
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✨ Рассчитать метрики",
                    callback_data=f"metrics|{date_from}|{date_to}|{label}|{reg_count}|{ftd_count}|{rd_count}|{clicks}|{unique_clicks}"
                )
            ],
            [
                InlineKeyboardButton("Назад", callback_data="back_mainmenu")
            ]
        ])
        await query.edit_message_text(msg_nometric, parse_mode="HTML", reply_markup=kb)
        return

    # Иначе
    await query.edit_message_text("Неизвестная команда", parse_mode="HTML")

# ------------------------------
# Показываем ЕДИНУЮ статистику + кнопка "Рассчитать метрики"
# ------------------------------
async def show_stats_unified(query, context, date_from, date_to, label):
    """
    1) /common => клики, подтверждённые, payout
    2) /conversions => registration, ftd, rdeposit
    3) Формируем единый текст
    4) Inline-кнопка "Рассчитать метрики"
    """
    ok_c, data_c = await get_common_data(date_from, date_to)
    if not ok_c:
        text = f"❗ {data_c}"
        # назад
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Назад", callback_data="back_mainmenu")]
        ])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        return

    # Парсим /common
    st = data_c.get("data",[{}])[0]
    gf = st.get("group_fields",[])
    date_info = gf[0].get("label") if gf else "N/A"
    clicks = st.get("click_count", 0)
    unique_clicks = st.get("click_unique_count", 0)
    conf = st.get("conversions",{}).get("confirmed", {})
    conf_count = conf.get("count", 0)
    conf_payout = conf.get("payout", 0)

    # Запрос /conversions => registration, ftd, rdeposit
    ok_r, data_r = await get_reg_ftd_rd(date_from, date_to)
    if not ok_r:
        # всё равно показываем хотя бы /common
        text = f"❗ {data_r}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Назад", callback_data="back_mainmenu")]
        ])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        return

    reg_count = data_r["registration"]
    ftd_count = data_r["ftd"]
    rd_count  = data_r["rdeposit"]

    # Строим итоговый текст
    final_msg = build_final_message(
        period_label=label,
        date_info=date_info,
        clicks=clicks,
        unique_clicks=unique_clicks,
        reg_count=reg_count,
        ftd_count=ftd_count,
        rd_count=rd_count,
        conf_count=conf_count,
        conf_payout=conf_payout,
        metrics_text=""
    )
    # Сохраняем в user_data, чтобы при добавлении метрик "прилепить" к нему
    context.user_data["last_stats_msg"] = final_msg

    # Кнопка "Рассчитать метрики" => "metrics|date_from|date_to|label|reg|ftd|rd|clicks|unique"
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✨ Рассчитать метрики",
                callback_data=f"metrics|{date_from}|{date_to}|{label}|{reg_count}|{ftd_count}|{rd_count}|{clicks}|{unique_clicks}"
            )
        ],
        [
            InlineKeyboardButton("Назад", callback_data="back_mainmenu")
        ]
    ])
    await query.edit_message_text(final_msg, parse_mode="HTML", reply_markup=kb)

# ------------------------------
# Пользователь вводит период вручную
# ------------------------------
async def text_handler_dates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Сценарий, когда пользователь выбрал "Свой период" и бот ждёт "YYYY-MM-DD,YYYY-MM-DD"
    """
    if context.user_data.get("awaiting_custom_period"):
        text = update.message.text.strip()
        if text.lower() == "назад":
            # Восстанавливаем меню выбора периода
            context.user_data["awaiting_custom_period"] = False
            inline_msg_id = context.user_data.get("inline_msg_id", None)
            if inline_msg_id:
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
                        InlineKeyboardButton("Назад", callback_data="back_mainmenu")
                    ]
                ])
                await update.message.delete()
                try:
                    await context.bot.edit_message_text(
                        text="Выберите период:",
                        chat_id=update.effective_chat.id,
                        message_id=inline_msg_id,
                        parse_mode="HTML",
                        reply_markup=kb
                    )
                except Exception as e:
                    logger.error(f"Ошибка при возврате к меню периодов: {e}")
            return

        # Парсим
        parts = text.split(",")
        if len(parts) != 2:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❗ Формат: YYYY-MM-DD,YYYY-MM-DD или 'Назад'."
            )
            return

        try:
            start_d = datetime.strptime(parts[0].strip(), "%Y-%m-%d").date()
            end_d   = datetime.strptime(parts[1].strip(), "%Y-%m-%d").date()
        except:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❗ Ошибка разбора дат. Попробуйте снова или 'Назад'."
            )
            return

        if start_d > end_d:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❗ Начальная дата больше конечной."
            )
            return

        context.user_data["awaiting_custom_period"] = False
        inline_msg_id = context.user_data["inline_msg_id"]
        await update.message.delete()

        date_from = f"{start_d} 00:00"
        date_to   = f"{end_d} 23:59"
        label = f"{start_d} - {end_d}"

        # Показываем объединённую статистику
        # Нужно edit_message_text(inline_msg_id)
        # имитируем вызов show_stats_unified
        # Но мы не вызываем callbackQueryHandler. Придётся вручную:
        class FakeQuery:
            def __init__(self, message_id, chat_id):
                self.message = type("Msg", (), {})()
                self.message.message_id = message_id
                self.message.chat_id = chat_id
            async def edit_message_text(self, *args, **kwargs):
                return await context.bot.edit_message_text(
                    chat_id=self.message.chat_id,
                    message_id=self.message.message_id,
                    *args, **kwargs
                )
            async def answer(self):
                pass

        fake_query = FakeQuery(inline_msg_id, update.effective_chat.id)
        await show_stats_unified(fake_query, context, date_from, date_to, label)

    else:
        # Другой случай
        pass

# ------------------------------
# Обработка Reply-кнопок (ЛК ПП / Получить статистику / Назад)
# ------------------------------
async def reply_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Удаляем сообщение пользователя
    await asyncio.sleep(1)
    try:
        await update.message.delete()
    except:
        pass

    # Удаляем старое сообщение бота
    await asyncio.sleep(1)
    last_id = context.user_data.get("last_msg_id")
    if last_id:
        try:
            await context.bot.delete_message(update.effective_chat.id, last_id)
        except:
            pass

    text = update.message.text.strip()

    if text == "ЛК ПП":
        link = "Ваш личный кабинет партнёра: https://cabinet.4rabetpartner.com/statistics"
        sent = await update.message.reply_text(link, parse_mode="HTML", reply_markup=get_main_menu())
        context.user_data["last_msg_id"] = sent.message_id
        return

    if text == "📊 Получить статистику":
        # Высылаем inline-меню
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
# 1) Проверяем, не вводит ли пользователь период
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler_dates), group=1)
# 2) Иначе — обычные Reply-кнопки
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_button_handler), group=2)
# 3) Инлайн-кнопки
telegram_app.add_handler(CallbackQueryHandler(inline_button_handler))

# ------------------------------
# Основной запуск
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    loop = asyncio.get_event_loop()
    loop.create_task(init_telegram_app())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
