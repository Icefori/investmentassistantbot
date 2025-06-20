import asyncio
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from dotenv import load_dotenv
from bot.scheduler.market_open import get_market_messages, MARKETS
from datetime import datetime, timedelta
from bot.scheduler.currency import fetch_exchange_rates_full, format_currency_message_structured
from bot.scheduler.take_profit import check_take_profit_alerts
from bot.db import connect_db
import os
import sys

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)

# Получить всех пользователей и их таймзоны
async def get_all_users_timezones():
    conn = await connect_db()
    rows = await conn.fetch("SELECT user_id, timezone FROM users")
    await conn.close()
    return [(r["user_id"], r["timezone"]) for r in rows]

# Получить всех пользователей (user_id)
async def get_all_users():
    conn = await connect_db()
    rows = await conn.fetch("SELECT user_id FROM users")
    await conn.close()
    return [r["user_id"] for r in rows]

async def send_daily_currency_update():
    try:
        today_rates, today_changes, week_rates, month_rates = await fetch_exchange_rates_full()
        message = format_currency_message_structured(today_rates, today_changes, week_rates, month_rates)
        users = await get_all_users()
        for user_id in users:
            await bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown")
        print("✅ Курсы валют отправлены")
    except Exception as e:
        print(f"⚠️ Ошибка при отправке курсов валют: {e}")

async def send_take_profit_alert(msg):
    try:
        users = await get_all_users()
        for user_id in users:
            await bot.send_message(chat_id=user_id, text=msg, parse_mode="Markdown")
        print("✅ Take Profit alert отправлен")
    except Exception as e:
        print(f"⚠️ Ошибка при отправке Take Profit alert: {e}")

# Универсальная рассылка уведомлений по рынкам с учетом user_id и timezone
async def send_market_notifications_to_all_users(event: str):
    """
    event: 'open' или 'close_soon'
    Проверяет для каждого пользователя его локальное время и отправляет уведомление, если наступило нужное событие.
    """
    users = await get_all_users_timezones()
    now_utc = datetime.utcnow().replace(second=0, microsecond=0)
    for user_id, tz_str in users:
        try:
            user_tz = pytz.timezone(tz_str)
        except Exception:
            print(f"❗ Не удалось определить таймзону для пользователя {user_id}: {tz_str}")
            continue
        now_local = datetime.now(user_tz).replace(second=0, microsecond=0)
        offset_sec = user_tz.utcoffset(now_local).total_seconds()
        gmt_offset = f"{int(offset_sec // 3600):+d}"

        for market in MARKETS:
            market_open_hour, market_open_minute = market["open"]
            market_close_hour, market_close_minute = market["close"]
            # Проверяем только по времени пользователя!
            if event == "open":
                messages = get_market_messages('open', user_tz, gmt_offset)
                for msg in messages:
                    await bot.send_message(chat_id=user_id, text=msg, parse_mode="Markdown")
            elif event == "close_soon":
                messages = get_market_messages('close_soon', user_tz, gmt_offset)
                for msg in messages:
                    await bot.send_message(chat_id=user_id, text=msg, parse_mode="Markdown")
    print(f"✅ Market {event} уведомления отправлены всем пользователям")

def start_scheduler(loop):
    tz = pytz.timezone("Europe/Amsterdam")
    scheduler = AsyncIOScheduler(timezone=tz, event_loop=loop)
    scheduler.add_job(
        send_daily_currency_update,
        trigger="cron",
        hour=8,
        minute=0,
        day_of_week="mon-fri"
    )
    scheduler.add_job(
        lambda: asyncio.create_task(check_take_profit_alerts(send_take_profit_alert)),
        trigger="cron",
        hour=8,
        minute=1,
        day_of_week="mon-fri"
    )
    # Новый универсальный способ: каждые 30 минут проверяем для всех пользователей их локальное время
    scheduler.add_job(
        send_market_notifications_to_all_users,
        args=['open'],
        trigger="cron",
        minute="0,30",
        day_of_week="mon-fri"
    )
    scheduler.add_job(
        send_market_notifications_to_all_users,
        args=['close_soon'],
        trigger="cron",
        minute="0,30",
        day_of_week="mon-fri"
    )
    scheduler.start()
    print("🕗 Планировщик запущен")

# ▶️ Функция для запуска планировщика (используется в main.py)
async def run_scheduler():
    loop = asyncio.get_running_loop()
    start_scheduler(loop)

    # Ручной запуск по аргументу (опционально)
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "currency":
            await send_daily_currency_update()
        elif arg == "market":
            await send_market_notifications_to_all_users('open')
        elif arg == "all":
            await send_daily_currency_update()
            await send_market_notifications_to_all_users('open')
    await asyncio.Event().wait()  # Держим event
