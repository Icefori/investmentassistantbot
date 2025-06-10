import asyncio
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot

# ⛳️ Импорт из подкаталога
from bot.scheduler.currency import fetch_exchange_rates, format_currency_message

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("OWNER_CHAT_ID")

async def send_daily_currency_update():
    try:
        rates = await fetch_exchange_rates()
        message = format_currency_message(rates)
        await bot.send_message(chat_id=CHAT_ID, text=message, parse_mode="HTML")
        print("✅ Курсы валют отправлены")
    except Exception as e:
        print(f"⚠️ Ошибка при отправке курсов валют: {e}")

def start_scheduler():
    tz = pytz.timezone("Europe/Amsterdam")
    scheduler = AsyncIOScheduler(timezone=tz)
    scheduler.add_job(send_daily_currency_update, trigger="date", hour=8, minute=0)
    scheduler.start()
    print("🕗 Планировщик запущен")

if __name__ == "__main__":
    asyncio.run(send_daily_currency_update())  # Один раз сразу
    start_scheduler()
    asyncio.get_event_loop().run_forever()