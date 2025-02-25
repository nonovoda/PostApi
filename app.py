import os
import logging
import asyncio
from datetime import datetime, timedelta
import httpx
from fastapi import FastAPI, Request
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

API_KEY = os.getenv("PP_API_KEY", "ВАШ_API_КЛЮЧ")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "ВАШ_ТОКЕН")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "ВАШ_CHAT_ID")
BASE_API_URL = "https://4rabet.api.alanbase.com/v1"
PORT = int(os.environ.get("PORT", 8000))

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()
telegram_app = Application.builder().token(TELEGRAM_TOKEN).build()

# ------------------------------
# Меню
# ------------------------------
def get_main_menu():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(text="📊 Получить статистику"), KeyboardButton(text="ЛК ПП")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )

def get_statistics_menu():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(text="📅 За сегодня")],
            [KeyboardButton(text="🗓 За период"), KeyboardButton(text="📆 За месяц")],
            [KeyboardButton(text="↩️ Назад")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

# ------------------------------
# Общая функция форматирования
# ------------------------------
async def format_common_stats(resp_json, period_label: str) -> str:
    # resp_json – результат /partner/statistic/common
    data = resp_json.get("data", [])
    if not data:
        return f"⚠️ Нет общей статистики ({period_label})."

    stat = data[0]
    group_fields = stat.get("group_fields", [])
    date_info = group_fields[0].get("label") if group_fields else "N/A"
    clicks = stat.get("click_count", 0)
    unique_clicks = stat.get("click_unique_count", 0)
    conversions = stat.get("conversions", {}).get("confirmed", {})
    confirmed_count = conversions.get("count", 0)
    confirmed_payout = conversions.get("payout", 0)

    txt = (
        f"<b>📊 Общая статистика ({period_label})</b>\n\n"
        f"🗓 <b>Дата(ы):</b> <i>{date_info}</i>\n"
        f"👁 <b>Клики:</b> <i>{clicks}</i> (уник: {unique_clicks})\n"
        f"✅ <b>Подтверждённые конверсии:</b> <i>{confirmed_count}</i>\n"
        f"💰 <b>Сумма выплат:</b> <i>{confirmed_payout} USD</i>\n"
    )
    return txt

# ------------------------------
# Суммарная детализация по целям
# ------------------------------
async def get_goals_detail(date_from: str, date_to: str) -> str:
    """
    Делаем запрос /partner/statistic/conversions с goal_keys[]=registration, ftd, bet, rdeposit
    Сгруппируем и вернем строку формата:
    Registration: X шт., payout=Y
    FTD: ...
    """
    # Подготовим параметры
    base_params = [
        ("timezone", "Europe/Moscow"),
        ("date_from", date_from),
        ("date_to", date_to),
        ("per_page", "500"),  # запас
    ]
    # Добавляем все нужные ключи
    for g in ["registration", "ftd", "bet", "rdeposit"]:
        base_params.append(("goal_keys[]", g))

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_API_URL}/partner/statistic/conversions",
                headers={"API-KEY": API_KEY, "Content-Type": "application/json"},
                params=base_params
            )
        if resp.status_code != 200:
            return f"⚠️ Ошибка детализации (goals): {resp.status_code} {resp.text}"

        data = resp.json().get("data", [])
        # Группируем
        # Пример: { 'registration': {'count': 2, 'payout': 10}, 'ftd': {...}, ... }
        goals_map = {
            "registration": {"count": 0, "payout": 0},
            "ftd": {"count": 0, "payout": 0},
            "bet": {"count": 0, "payout": 0},
            "rdeposit": {"count": 0, "payout": 0},
        }
        for c in data:
            g = c.get("goal", {}).get("key")  # registration, ftd, bet, rdeposit
            payout = c.get("payout", 0)
            if g in goals_map:
                goals_map[g]["count"] += 1
                goals_map[g]["payout"] += float(payout)

        # Формируем текст
        txt = "<b>Суммарная детализация по целям</b>:\n"
        # Добавим эмодзи, если хотите
        emoji_map = {
            "registration": "🆕",
            "ftd": "💵",
            "bet": "🎰",
            "rdeposit": "🔄"
        }
        for key, val in goals_map.items():
            em = emoji_map.get(key, "")
            txt += (
                f"{em} <b>{key}</b>: <i>{val['count']}</i> шт., payout= <i>{val['payout']}</i>\n"
            )
        return txt

    except Exception as e:
        return f"⚠️ Ошибка при загрузке детализации: {e}"

# ------------------------------
# /webhook (по аналогии, если нужно)
# ------------------------------
@app.post("/webhook")
async def webhook_handler(request: Request):
    try:
        data = await request.json()
        if "update_id" in data:
            update = Update.de_json(data, telegram_app.bot)
            if not telegram_app.running:
                await init_telegram_app()
            await telegram_app.process_update(update)
        else:
            pass  # postback
    except:
        pass
    return {"status": "ok"}

# ------------------------------
# Команда /start
# ------------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(1)
    last_msg_id = context.user_data.get("last_bot_message_id")
    if last_msg_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_msg_id)
        except Exception as e:
            logger.debug(f"Не удалось удалить предыдущее сообщение бота: {e}")

    main_keyboard = get_main_menu()
    text = "Привет! Выберите команду:"
    sent_msg = await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_keyboard)
    context.user_data["last_bot_message_id"] = sent_msg.message_id

# ------------------------------
# Обработчик кнопок
# ------------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    # Удаляем сообщение пользователя
    await asyncio.sleep(1)
    try:
        await update.message.delete()
    except:
        pass

    # Удаляем предыдущее сообщение бота
    await asyncio.sleep(1)
    last_id = context.user_data.get("last_bot_message_id")
    if last_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_id)
        except:
            pass

    text = update.message.text.strip()
    logger.debug(f"Поступила команда: {text}")

    if text == "ЛК ПП":
        link_text = "Ваш личный кабинет партнёра: https://cabinet.4rabetpartner.com/statistics"
        msg = await update.message.reply_text(link_text, parse_mode="HTML", reply_markup=get_main_menu())
        context.user_data["last_bot_message_id"] = msg.message_id
        return

    if text == "📊 Получить статистику":
        st_menu = get_statistics_menu()
        msg = await update.message.reply_text("Выберите период статистики:", parse_mode="HTML", reply_markup=st_menu)
        context.user_data["last_bot_message_id"] = msg.message_id
        return

    if text == "↩️ Назад":
        # Возвращаемся в главное меню
        mk = get_main_menu()
        msg = await update.message.reply_text("Возврат в главное меню:", parse_mode="HTML", reply_markup=mk)
        context.user_data["last_bot_message_id"] = msg.message_id
        return

    if text == "📅 За сегодня":
        now_str = datetime.now().strftime("%Y-%m-%d")
        date_from = f"{now_str} 00:00"
        date_to = f"{now_str} 23:59"
        period_label = "За сегодня"

        # 1) Запрашиваем /common
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
                data = resp.json()
                comm_str = await format_common_stats(data, period_label)
            else:
                comm_str = f"⚠️ Ошибка /common: {resp.status_code} {resp.text}"
        except Exception as e:
            comm_str = f"⚠️ Ошибка: {e}"

        # 2) Запрашиваем суммарную детализацию (registration, ftd, bet, rdeposit)
        detail_str = await get_goals_detail(date_from, date_to)

        # Итоговое сообщение
        full_txt = comm_str + "\n\n" + detail_str
        msg = await update.message.reply_text(full_txt, parse_mode="HTML", reply_markup=get_main_menu())
        context.user_data["last_bot_message_id"] = msg.message_id
        return

    if text == "📆 За месяц":
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=30)
        date_from = f"{start_date.strftime('%Y-%m-%d')} 00:00"
        date_to = f"{end_date.strftime('%Y-%m-%d')} 23:59"
        period_label = f"За {start_date} - {end_date}"

        # 1) /common
        try:
            # Можно, как у вас, покадрово суммировать, но здесь сделаем единый запрос
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{BASE_API_URL}/partner/statistic/common",
                    headers={"API-KEY": API_KEY},
                    params={
                        "group_by": "day",  # или month, если надо
                        "timezone": "Europe/Moscow",
                        "date_from": date_from,
                        "date_to": date_to,
                        "currency_code": "USD"
                    }
                )
            if resp.status_code == 200:
                data = resp.json()
                comm_str = await format_common_stats(data, period_label)
            else:
                comm_str = f"⚠️ Ошибка /common: {resp.status_code} {resp.text}"
        except Exception as e:
            comm_str = f"⚠️ Ошибка: {e}"

        # 2) Детализация (общее кол-во и payout по registration, ftd, bet, rdeposit)
        detail_str = await get_goals_detail(date_from, date_to)

        full_txt = comm_str + "\n\n" + detail_str
        msg = await update.message.reply_text(full_txt, parse_mode="HTML", reply_markup=get_main_menu())
        context.user_data["last_bot_message_id"] = msg.message_id
        return

    if text == "🗓 За период":
        # Спрашиваем у пользователя даты
        await update.message.reply_text("Введите период (YYYY-MM-DD,YYYY-MM-DD):", parse_mode="HTML")
        context.user_data["awaiting_period"] = True
        return

    # Если пользователь вводит период вручную
    if context.user_data.get("awaiting_period"):
        context.user_data["awaiting_period"] = False
        parts = text.split(",")
        if len(parts) != 2:
            msg = await update.message.reply_text(
                "Неверный формат. Введите в формате YYYY-MM-DD,YYYY-MM-DD",
                parse_mode="HTML",
                reply_markup=get_main_menu()
            )
            context.user_data["last_bot_message_id"] = msg.message_id
            return
        try:
            start_d = datetime.strptime(parts[0].strip(), "%Y-%m-%d").date()
            end_d = datetime.strptime(parts[1].strip(), "%Y-%m-%d").date()
        except:
            msg = await update.message.reply_text("Ошибка парсинга даты.", parse_mode="HTML", reply_markup=get_main_menu())
            context.user_data["last_bot_message_id"] = msg.message_id
            return
        if start_d > end_d:
            msg = await update.message.reply_text("Начальная дата больше конечной!", parse_mode="HTML", reply_markup=get_main_menu())
            context.user_data["last_bot_message_id"] = msg.message_id
            return

        date_from = f"{start_d} 00:00"
        date_to = f"{end_d} 23:59"
        period_label = f"{start_d} - {end_d}"

        # /common
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
                data = resp.json()
                comm_str = await format_common_stats(data, period_label)
            else:
                comm_str = f"⚠️ Ошибка /common: {resp.status_code} {resp.text}"
        except Exception as e:
            comm_str = f"⚠️ Ошибка: {e}"

        # Детализация
        detail_str = await get_goals_detail(date_from, date_to)
        full_txt = comm_str + "\n\n" + detail_str
        msg = await update.message.reply_text(full_txt, parse_mode="HTML", reply_markup=get_main_menu())
        context.user_data["last_bot_message_id"] = msg.message_id
        return

    # Если команда не распознана
    msg = await update.message.reply_text("Неизвестная команда.", parse_mode="HTML", reply_markup=get_main_menu())
    context.user_data["last_bot_message_id"] = msg.message_id

# ------------------------------
# /start
# ------------------------------
telegram_app.add_handler(CommandHandler("start", start_command))
# ------------------------------
# Обработка команд (Reply-кнопки)
# ------------------------------
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))

# ------------------------------
# Запуск
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    loop = asyncio.get_event_loop()
    loop.create_task(telegram_app.initialize())
    loop.create_task(telegram_app.start())
    uvicorn.run(app, host="0.0.0.0", port=PORT)
