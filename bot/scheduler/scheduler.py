import asyncio
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from dotenv import load_dotenv
from bot.scheduler.market_open import get_market_messages, MARKETS
from datetime import datetime, timedelta
from bot.scheduler.currency import fetch_exchange_rates_full, format_currency_message_structured
from bot.scheduler.take_profit import check_take_profit_alerts
import os
import sys

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("OWNER_CHAT_ID")
bot = Bot(token=BOT_TOKEN)

async def send_daily_currency_update():
    try:
        today_rates, today_changes, week_rates, month_rates = await fetch_exchange_rates_full()
        message = format_currency_message_structured(today_rates, today_changes, week_rates, month_rates)
        await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="Markdown")
        print("✅ Курсы валют отправлены")
    except Exception as e:
        print(f"⚠️ Ошибка при отправке курсов валют: {e}")

async def send_take_profit_alert(msg):
    try:
        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")
        print("✅ Take Profit alert отправлен")
    except Exception as e:
        print(f"⚠️ Ошибка при отправке Take Profit alert: {e}")

async def send_market_open_notifications():
    now_ams = datetime.now(pytz.timezone("Europe/Amsterdam"))
    messages = get_market_messages('open', now_ams)
    for msg in messages:
        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")
    print("✅ Market open уведомления отправлены")

async def send_market_close_soon_notifications():
    now_ams = datetime.now(pytz.timezone("Europe/Amsterdam"))
    messages = get_market_messages('close_soon', now_ams)
    for msg in messages:
        await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")
    print("✅ Market close soon уведомления отправлены")

def schedule_market_notifications(scheduler):
    tz_ams = pytz.timezone("Europe/Amsterdam")
    now = datetime.now(tz_ams)
    today = now.date()
    for market in MARKETS:
        market_tz = pytz.timezone(market["tz"])
        # Время открытия
        open_dt = market_tz.localize(datetime.combine(today, datetime.min.time()) + timedelta(hours=market["open"][0], minutes=market["open"][1]))
        open_dt_ams = open_dt.astimezone(tz_ams)
        if open_dt_ams > now:
            scheduler.add_job(
                send_market_open_notifications,
                trigger="date",
                run_date=open_dt_ams,
                id=f"{market['name']}_open_{today}"
            )
        # За час до закрытия
        close_dt = market_tz.localize(datetime.combine(today, datetime.min.time()) + timedelta(hours=market["close"][0], minutes=market["close"][1]))
        close_soon_dt_ams = (close_dt - timedelta(hours=1)).astimezone(tz_ams)
        if close_soon_dt_ams > now:
            scheduler.add_job(
                send_market_close_soon_notifications,
                trigger="date",
                run_date=close_soon_dt_ams,
                id=f"{market['name']}_close_soon_{today}"
            )

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
    # Каждый день в 00:01 пересчитываем расписание уведомлений на сегодня
    scheduler.add_job(
        lambda: schedule_market_notifications(scheduler),
        trigger="cron",
        hour=0,
        minute=1,
        day_of_week="mon-fri"
    )
    # Первый запуск при старте
    schedule_market_notifications(scheduler)
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
            await send_market_open_notifications()
        elif arg == "all":
            await send_daily_currency_update()
            await send_market_open_notifications()
    await asyncio.Event().wait()  # Держим event loop
