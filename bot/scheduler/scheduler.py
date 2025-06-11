import asyncio
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from dotenv import load_dotenv
from bot.scheduler.market_open import get_market_messages
from datetime import datetime

# ⛳️ Импорт из подкаталога
from bot.scheduler.currency import fetch_exchange_rates_full, format_currency_message_structured
from bot.scheduler.take_profit import check_take_profit_alerts

import os

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("OWNER_CHAT_ID")

bot = Bot(token=BOT_TOKEN)

print(f"BOT_TOKEN из env: {BOT_TOKEN}")

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

def start_scheduler():
    tz = pytz.timezone("Europe/Amsterdam")
    scheduler = AsyncIOScheduler(timezone=tz)
    # Курсы валют — каждый день в 8:00, кроме выходных
    scheduler.add_job(
        lambda: asyncio.create_task(send_daily_currency_update()),
        trigger="cron",
        hour=8,
        minute=0,
        day_of_week="mon-fri"
    )
    # Take Profit — каждый день в 8:01, кроме выходных
    scheduler.add_job(
        lambda: asyncio.create_task(check_take_profit_alerts(send_take_profit_alert)),
        trigger="cron",
        hour=8,
        minute=1,
        day_of_week="mon-fri"
    )
    # Открытие рынка — каждый день в 11:30, кроме выходных
    scheduler.add_job(
        lambda: asyncio.create_task(send_market_open_notifications()),
        trigger="cron",
        hour=11,
        minute=30,
        day_of_week="mon-fri"
    )
    scheduler.start()
    print("🕗 Планировщик запущен")

if __name__ == "__main__":
    asyncio.run(send_daily_currency_update())  # Один раз сразу
    start_scheduler()
    asyncio.get_event_loop().run_forever()

if __name__ == "__main__":
        import sys
    
        async def manual_test():
            if len(sys.argv) > 1 and sys.argv[1] == "market":
                await send_market_open_notifications()
            else:
                await send_daily_currency_update()
    
        asyncio.run(manual_test())