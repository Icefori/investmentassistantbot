import asyncio
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from dotenv import load_dotenv

# ⛳️ Импорт из подкаталога
from bot.scheduler.currency import fetch_exchange_rates, format_currency_message
from bot.scheduler.take_profit import check_take_profit_alerts

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("OWNER_CHAT_ID")

bot = Bot(token=BOT_TOKEN)

print(f"BOT_TOKEN из env: {BOT_TOKEN}")

async def send_daily_currency_update():
    try:
        rates = await fetch_exchange_rates()
        message = format_currency_message(rates)
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

def start_scheduler():
    tz = pytz.timezone("Europe/Amsterdam")
    scheduler = AsyncIOScheduler(timezone=tz)
    # Курсы валют — каждый день в 8:00, кроме выходных
    scheduler.add_job(
        send_daily_currency_update,
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
    scheduler.start()
    print("🕗 Планировщик запущен")

if __name__ == "__main__":
    asyncio.run(send_daily_currency_update())  # Один раз сразу
    start_scheduler()
    asyncio.get_event_loop().run_forever()