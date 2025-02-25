import os
import logging
import asyncio
from datetime import datetime, timedelta
import httpx

from fastapi import FastAPI, Request
from telegram import (
    Update,
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
API_KEY = os.getenv("PP_API_KEY", "YOUR_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "YOUR_TELEGRAM_TOKEN")
BASE_API_URL = "https://4rabet.api.alanbase.com/v1"
PORT = int(os.environ.get("PORT", 8000))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# ------------------------------
# Создание экземпляра FastAPI
# ------------------------------
app = FastAPI()

# ------------------------------
# Инициализация Telegram-бота
# ------------------------------
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

async def init_telegram_app():
    await telegram_app.initialize()
    await telegram_app.start()
    logger.info("Telegram bot started!")

# ------------------------------
# Утилиты форматирования
# ------------------------------
async def format_common_stats(data, period_label: str) -> str:
    """
    Оформляем общую статистику (response /partner/statistic/common)
    """
    arr = data.get("data", [])
    if not arr:
        return f"⚠️ <i>Нет данных ({period_label})</i>"

    stat = arr[0]
    # Пример извлечения:
    date_info = (stat.get("group_fields", [{}])[0].get("label", "")) if stat.get("group_fields") else "N/A"
    clicks = stat.get("click_count", 0)
    unique_clicks = stat.get("click_unique_count", 0)
    conversions = stat.get("conversions", {}).get("confirmed", {})
    count_conf = conversions.get("count", 0)
    payout_conf = conversions.get("payout", 0)

    msg = (
        f"<b>📊 Общая статистика ({period_label})</b>\n\n"
        f"🗓 Дата(ы): <i>{date_info}</i>\n"
        f"👁 Клики: <b>{clicks}</b> (уник. {unique_clicks})\n"
        f"✅ Подтверждённые конверсии: <b>{count_conf}</b>\n"
        f"💰 Выплаты: <b>{payout_conf} USD</b>\n"
    )
    return msg

def format_conversions_table(conv_list) -> str:
    """
    Красивая «таблица» конверсий, используя <code>...</code> для моноширинного шрифта.
    Добавим эмодзи и HTML-выделение.
    """
    if not conv_list:
        return "⚠️ <i>Нет конверсий по выбранным параметрам</i>"

    header = (
        "  ID         |     GOAL      |  STATUS   | PAYOUT\n"
        "-------------+---------------+-----------+-------\n"
    )
    body = ""
    for c in conv_list:
        cid = str(c.get("conversion_id", ""))
        goal_key = c.get("goal", {}).get("key", "")
        status = c.get("status", "")
        payout = str(c.get("payout", "0"))

        # Подрезаем/выравниваем
        cid_str = cid[:11].ljust(11)
        goal_str = goal_key[:10].ljust(10)
        stat_str = status[:9].ljust(9)
        pay_str = payout[:5].rjust(5)
        body += f"{cid_str} | {goal_str} | {stat_str} | {pay_str}\n"

    text = (
        "🎯 <b>Детализированные конверсии</b>\n\n"
        "<code>"
        + header
        + body
        + "</code>"
    )
    return text


# ------------------------------
# Обработка postback (GET/POST) – если вам нужно
# ------------------------------
@app.api_route("/webhook", methods=["GET", "POST"])
async def webhook_handler(request: Request):
    """
    Унифицированный webhook: либо Telegram-обновление (POST JSON), либо postback GET/POST
    """
    # ... можно оставить как есть, если уже реализовано ...
    try:
        data = await request.json()
        if "update_id" in data:
            update = Update.de_json(data, telegram_app.bot)
            if not telegram_app.running:
                await init_telegram_app()
            await telegram_app.process_update(update)
            return {"status": "ok"}
        else:
            # postback
            ...
            return {"status": "ok"}
    except:
        # Возможно GET postback
        return {"status": "ok"}

# ------------------------------
# /start – отправляем одно сообщение с inline-кнопками
# ------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Приветствие
    text = (
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Я ваш бот для статистики. Выберите действие:"
    )

    # Кнопки: Получить статистику / ЛК ПП (пример) / ... 
    kb = [
        [InlineKeyboardButton("📊 Статистика", callback_data="menu_stats")],
        [InlineKeyboardButton("🔗 ЛК ПП", callback_data="lkpp")],
        [InlineKeyboardButton("❌ Выход", callback_data="exit")]
    ]
    reply_markup = InlineKeyboardMarkup(kb)

    # Отправляем одно сообщение (сохраняем его ID, если нужно).
    sent = await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=reply_markup
    )
    # Сохраняем msg_id, если потребуется
    context.user_data["main_msg_id"] = sent.message_id

# ------------------------------
# Обработчик inline-кнопок (едитим тот же месседж)
# ------------------------------
async def inline_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data  # например "menu_stats", "lkpp", "exit", "period_today" ...
    logger.debug(f"Callback data: {data}")

    # ------------------------------------
    # ГЛАВНОЕ МЕНЮ
    # ------------------------------------
    if data == "menu_stats":
        # При нажатии "📊 Статистика" – показываем меню выбора периода
        text = "📅 <b>Какой период статистики?</b>"
        kb = [
            [InlineKeyboardButton("Сегодня", callback_data="period_today")],
            [InlineKeyboardButton("За месяц", callback_data="period_month")],
            [InlineKeyboardButton("За период", callback_data="period_custom")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_mainmenu")]
        ]
        markup = InlineKeyboardMarkup(kb)
        # Редактируем текущее сообщение
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        return

    elif data == "lkpp":
        # Личный кабинет партнёра – просто даём ссылку
        text = "🔗 Личный кабинет: https://cabinet.4rabetpartner.com/statistics\n\n⬅️ <i>Возвращаю в меню...</i>"
        await query.edit_message_text(text, parse_mode="HTML")
        # Показываем главное меню
        kb = [
            [InlineKeyboardButton("📊 Статистика", callback_data="menu_stats")],
            [InlineKeyboardButton("🔗 ЛК ПП", callback_data="lkpp")],
            [InlineKeyboardButton("❌ Выход", callback_data="exit")]
        ]
        await asyncio.sleep(2)
        await query.edit_message_text(
            "👋 <b>Добро пожаловать!</b>\n\nЯ ваш бот для статистики. Выберите действие:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    elif data == "exit":
        # Выход: редактируем сообщение, убираем кнопки
        await query.edit_message_text("👋 <i>До свидания!</i>", parse_mode="HTML")
        return

    elif data == "back_mainmenu":
        # Вернуться в главное меню
        kb = [
            [InlineKeyboardButton("📊 Статистика", callback_data="menu_stats")],
            [InlineKeyboardButton("🔗 ЛК ПП", callback_data="lkpp")],
            [InlineKeyboardButton("❌ Выход", callback_data="exit")]
        ]
        text = "👋 <b>Добро пожаловать!</b>\n\nЯ ваш бот для статистики. Выберите действие:"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        return

    # ------------------------------------
    # МЕНЮ СТАТИСТИКИ – выбор периода
    # ------------------------------------
    elif data == "period_today":
        # За сегодня
        period_label = "Сегодня"
        date_str = datetime.now().strftime("%Y-%m-%d")
        date_from = f"{date_str} 00:00"
        date_to = f"{date_str} 23:59"

        common_text, inline_kb = await get_common_stat_and_show_details_menu(
            date_from, date_to, period_label
        )
        await query.edit_message_text(common_text, parse_mode="HTML", reply_markup=inline_kb)
        return

    elif data == "period_month":
        # За последний месяц
        now = datetime.now()
        end_date = now.date()
        start_date = (end_date - timedelta(days=30))
        date_from = f"{start_date} 00:00"
        date_to = f"{end_date} 23:59"
        period_label = "Последние 30 дней"

        common_text, inline_kb = await get_common_stat_and_show_details_menu(
            date_from, date_to, period_label
        )
        await query.edit_message_text(common_text, parse_mode="HTML", reply_markup=inline_kb)
        return

    elif data == "period_custom":
        # За период – нужно попросить пользователя ввести даты
        # Переходим в "ожидание" (user_data["awaiting_period"] = True), но не удаляем сообщение,
        # а редактируем его, чтобы показать инструкцию
        context.user_data["awaiting_period"] = True
        text = (
            "📅 <b>Введите даты</b> в формате:\n"
            "<code>YYYY-MM-DD,YYYY-MM-DD</code>\n\n"
            "Например: <i>2025-02-01,2025-02-10</i>\n"
            "⬅️ Или нажмите Назад."
        )
        kb = [[InlineKeyboardButton("⬅️ Назад", callback_data="menu_stats")]]
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        return

    elif data.startswith("back_to_stats|"):
        # Например: "back_to_stats|2025-01-01 00:00|2025-01-05 23:59|Мой период"
        parts = data.split("|")
        date_from = parts[1]
        date_to = parts[2]
        period_label = parts[3]
        # Снова показываем общую статистику
        common_text, inline_kb = await get_common_stat_and_show_details_menu(
            date_from, date_to, period_label
        )
        await query.edit_message_text(common_text, parse_mode="HTML", reply_markup=inline_kb)
        return

    # ------------------------------------
    # ДЕТАЛИЗАЦИЯ – первый шаг: выбор цели
    # ------------------------------------
    elif data.startswith("details_first|"):
        # "details_first|2025-01-01 00:00|2025-01-10 23:59|Мой период"
        parts = data.split("|")
        date_from = parts[1]
        date_to = parts[2]
        label = parts[3]
        # Показываем меню целей
        text = (
            f"🔎 <b>Детализация за период:</b> {label}\n\n"
            "Выберите цель (goal):"
        )
        kb = [
            [
                InlineKeyboardButton("Registration", callback_data=f"details_goal|registration|{date_from}|{date_to}|{label}"),
                InlineKeyboardButton("FTD", callback_data=f"details_goal|ftd|{date_from}|{date_to}|{label}")
            ],
            [
                InlineKeyboardButton("Bets", callback_data=f"details_goal|bet|{date_from}|{date_to}|{label}"),
                InlineKeyboardButton("RDS", callback_data=f"details_goal|rdeposit|{date_from}|{date_to}|{label}")
            ],
            [
                InlineKeyboardButton("Все цели", callback_data=f"details_goal|all|{date_from}|{date_to}|{label}")
            ],
            [
                InlineKeyboardButton("⬅️ Назад", callback_data=f"back_to_stats|{date_from}|{date_to}|{label}")
            ]
        ]
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    # ------------------------------------
    # ДЕТАЛИЗАЦИЯ – второй шаг: показываем список
    # ------------------------------------
    elif data.startswith("details_goal|"):
        # "details_goal|registration|2025-01-01 00:00|2025-01-10 23:59|Мой период"
        parts = data.split("|")
        gkey = parts[1]
        date_from = parts[2]
        date_to = parts[3]
        label = parts[4]

        # формируем параметры
        base_params = [
            ("timezone", "Europe/Moscow"),
            ("date_from", date_from),
            ("date_to", date_to),
            ("per_page", "100"),
        ]

        if gkey == "all":
            # goals = ["registration","ftd","bet","rdeposit"]
            for x in ["registration","ftd","bet","rdeposit"]:
                base_params.append(("goal_keys[]", x))
        else:
            base_params.append(("goal_keys[]", gkey))

        # Делаем запрос
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{BASE_API_URL}/partner/statistic/conversions",
                    headers={"API-KEY": API_KEY, "Content-Type": "application/json"},
                    params=base_params
                )
            if resp.status_code == 200:
                data_json = resp.json()
                conv_list = data_json.get("data", [])
                # Возьмём, например, первые 50
                conv_list = conv_list[:50]
                text_table = format_conversions_table(conv_list)
                text_head = f"🔎 <b>Детализация: {gkey if gkey!='all' else 'все цели'} ({label})</b>\n\n"
                final_text = text_head + text_table
            else:
                final_text = f"Ошибка API {resp.status_code}: {resp.text}"
        except Exception as e:
            final_text = f"⚠️ Ошибка запроса: {e}"

        # Кнопка «Назад», возвращает к выбору цели
        kb = [
            [
                InlineKeyboardButton("⬅️ Назад", callback_data=f"details_first|{date_from}|{date_to}|{label}")
            ]
        ]
        await query.edit_message_text(final_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
        return

    # ------------------------------------
    # Если пришло что-то неописанное
    # ------------------------------------
    else:
        await query.edit_message_text("⚠️ Неизвестная команда", parse_mode="HTML")


# ------------------------------
# Вспомогательная функция
# ------------------------------
async def get_common_stat_and_show_details_menu(date_from, date_to, label: str):
    """
    Запрашиваем /partner/statistic/common, формируем текст, прикрепляем кнопку "Детализация" (первый шаг).
    Возвращаем (text, inline_markup).
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_API_URL}/partner/statistic/common",
                headers={"API-KEY": API_KEY, "Content-Type": "application/json"},
                params={
                    "group_by": "day",
                    "timezone": "Europe/Moscow",
                    "date_from": date_from,
                    "date_to": date_to,
                    "currency_code": "USD"
                }
            )
        if resp.status_code == 200:
            data = resp.json()
            common_txt = await format_common_stats(data, label)
        else:
            common_txt = f"⚠️ Ошибка API {resp.status_code}: {resp.text}"
    except Exception as e:
        common_txt = f"⚠️ Ошибка запроса: {e}"

    # Добавляем кнопку "Детализация"
    # callback_data: "details_first|date_from|date_to|label"
    kb = [
        [
            InlineKeyboardButton("🔎 Детализация", callback_data=f"details_first|{date_from}|{date_to}|{label}")
        ],
        [
            InlineKeyboardButton("⬅️ Назад", callback_data="menu_stats")
        ]
    ]
    return common_txt, InlineKeyboardMarkup(kb)


# ------------------------------
# Handler для user input (когда вводят даты)
# ------------------------------
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_period"):
        # Пользователь вводит даты
        text = update.message.text
        # Стираем флаг
        context.user_data["awaiting_period"] = False

        await update.message.delete()  # удалим введённое сообщение

        # Попробуем распарсить
        parts = text.split(",")
        if len(parts) != 2:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=context.user_data["main_msg_id"],
                text="⚠️ Неверный формат. Попробуйте ещё раз.",
                parse_mode="HTML"
            )
            return

        try:
            start_date = datetime.strptime(parts[0].strip(), "%Y-%m-%d").date()
            end_date = datetime.strptime(parts[1].strip(), "%Y-%m-%d").date()
        except:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=context.user_data["main_msg_id"],
                text="⚠️ Ошибка парсинга дат. Формат: YYYY-MM-DD,YYYY-MM-DD",
                parse_mode="HTML"
            )
            return

        if start_date > end_date:
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=context.user_data["main_msg_id"],
                text="⚠️ Начальная дата больше конечной!",
                parse_mode="HTML"
            )
            return

        date_from = f"{start_date} 00:00"
        date_to = f"{end_date} 23:59"
        label = f"{start_date} - {end_date}"
        # Теперь показываем общую статистику за период
        text_stats, kb = await get_common_stat_and_show_details_menu(date_from, date_to, label)
        await context.bot.edit_message_text(
            text=text_stats,
            parse_mode="HTML",
            chat_id=update.effective_chat.id,
            message_id=context.user_data["main_msg_id"],
            reply_markup=kb
        )
    else:
        # В любом другом случае (не ввод дат) – игнорируем
        pass

# ------------------------------
# Регистрация хэндлеров
# ------------------------------
telegram_app.add_handler(CommandHandler("start", start_command))
telegram_app.add_handler(CallbackQueryHandler(inline_handler))
# Когда пользователь вводит текст (например, даты) – этот хэндлер
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

# ------------------------------
# Запуск приложения
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    loop = asyncio.get_event_loop()
    loop.create_task(init_telegram_app())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
