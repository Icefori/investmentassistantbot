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

def get_market_messages(event: str, now_local: datetime, gmt_offset: str):
    """
    event: 'open' или 'close_soon'
    now_local: локальное время пользователя (datetime)
    gmt_offset: строка, например '+6' или '-3'
    """
    messages = []
    grouped = {}

    for market in MARKETS:
        market_tz = pytz.timezone(market["tz"])
        today = now_local.astimezone(market_tz).date()
        open_dt = market_tz.localize(datetime.combine(today, datetime.min.time()) + timedelta(hours=market["open"][0], minutes=market["open"][1]))
        close_dt = market_tz.localize(datetime.combine(today, datetime.min.time()) + timedelta(hours=market["close"][0], minutes=market["close"][1]))
        # Сравниваем по локальному времени пользователя
        if event == "open":
            key_dt = now_local.replace(hour=market["open"][0], minute=market["open"][1], second=0, microsecond=0)
            if now_local.replace(second=0, microsecond=0) == key_dt:
                grouped.setdefault(key_dt, []).append(market)
        elif event == "close_soon":
            key_dt = now_local.replace(hour=market["close"][0] - 1, minute=market["close"][1], second=0, microsecond=0)
            if now_local.replace(second=0, microsecond=0) == key_dt:
                grouped.setdefault(key_dt, []).append(market)

    for group in grouped.values():
        names = " / ".join(f"{m['emoji']} *{m['name']}*" for m in group)
        if event == "open":
            open_time = group[0]["open"]
            close_time = group[0]["close"]
            messages.append(
                f"{names} — открытие торгов!\n"
                f"🟢 Биржа открыта с {open_time[0]:02}:{open_time[1]:02} до {close_time[0]:02}:{close_time[1]:02} (GMT{gmt_offset})\n"
                f"Удачных сделок! 🚀"
            )
        elif event == "close_soon":
            close_time = group[0]["close"]
            messages.append(
                f"{names} — до закрытия торгов остался 1 час!\n"
                f"🔔 Биржа закроется в {close_time[0]:02}:{close_time[1]:02} (GMT{gmt_offset})\n"
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