import pytz
from datetime import datetime, timedelta

# Время открытия/закрытия бирж (по времени Астаны и EST)
MARKETS = [
    {
        "name": "KASE",
        "open": (11, 30),
        "close": (17, 0),
        "tz": "Asia/Almaty",
        "emoji": "🇰🇿"
    },
    {
        "name": "KASE Global",
        "open": (11, 30),
        "close": (22, 0),
        "tz": "Asia/Almaty",
        "emoji": "🌍"
    },
    {
        "name": "AIX",
        "open": (11, 30),
        "close": (17, 0),
        "tz": "Asia/Almaty",
        "emoji": "🏦"
    },
    {
        "name": "NASDAQ",
        "open": (9, 30),
        "close": (16, 0),
        "tz": "America/New_York",
        "emoji": "🇺🇸"
    }
]

def get_market_messages(event: str, now_ams: datetime):
    """event: 'open' или 'close_soon'"""
    messages = []
    for market in MARKETS:
        market_tz = pytz.timezone(market["tz"])
        ams_tz = pytz.timezone("Europe/Amsterdam")
        today = now_ams.astimezone(market_tz).date()
        open_dt = market_tz.localize(datetime.combine(today, datetime.min.time()) + timedelta(hours=market["open"][0], minutes=market["open"][1]))
        close_dt = market_tz.localize(datetime.combine(today, datetime.min.time()) + timedelta(hours=market["close"][0], minutes=market["close"][1]))
        # Переводим в Амстердам
        open_dt_ams = open_dt.astimezone(ams_tz)
        close_dt_ams = close_dt.astimezone(ams_tz)
        now = now_ams.replace(second=0, microsecond=0)

        if event == "open" and now == open_dt_ams.replace(second=0, microsecond=0):
            messages.append(
                f"{market['emoji']} *{market['name']}* — открытие торгов!\n"
                f"🟢 Биржа открыта с {open_dt_ams.strftime('%H:%M')} до {close_dt_ams.strftime('%H:%M')} (по Амстердаму)\n"
                f"Удачных сделок! 🚀"
            )
        elif event == "close_soon" and now == (close_dt_ams - timedelta(hours=1)).replace(second=0, microsecond=0):
            messages.append(
                f"{market['emoji']} *{market['name']}* — до закрытия торгов остался 1 час!\n"
                f"🔔 Биржа закроется в {close_dt_ams.strftime('%H:%M')} (по Амстердаму)\n"
                f"Проверьте свои позиции и заявки! ⏳"
            )
    return messages

# Пример использования в планировщике:
# В 11:30, 16:00, 21:00 и т.д. по Амстердаму вызывайте get_market_messages('open', now_ams) или get_market_messages('close_soon', now_ams)
# и отправляйте все сообщения из списка в Telegram

# Пример функции для планировщика:
# async def send_market_notifications(bot, chat_id):
#     now_ams = datetime.now(pytz.timezone("Europe/Amsterdam"))
#     for event in ["open", "close_soon"]:
#         messages = get_market_messages(event, now_ams)
#         for msg in messages:
#             await bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")