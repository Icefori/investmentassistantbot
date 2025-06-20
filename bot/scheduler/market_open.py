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

def get_market_messages(event: str, user_tz: pytz.BaseTzInfo, gmt_offset: str):
    """
    event: 'open' или 'close_soon'
    user_tz: pytz-таймзона пользователя
    gmt_offset: строка, например '+2' или '-3'
    """
    messages = []
    now_local = datetime.now(user_tz).replace(second=0, microsecond=0)
    lines = []
    for market in MARKETS:
        market_tz = pytz.timezone(market["tz"])
        today_market = datetime.now(market_tz).date()
        # Время открытия/закрытия в TZ биржи
        open_dt_market = market_tz.localize(datetime.combine(today_market, datetime.min.time()) + timedelta(hours=market["open"][0], minutes=market["open"][1]))
        close_dt_market = market_tz.localize(datetime.combine(today_market, datetime.min.time()) + timedelta(hours=market["close"][0], minutes=market["close"][1]))
        # Переводим в локальное время пользователя
        open_dt_local = open_dt_market.astimezone(user_tz)
        close_dt_local = close_dt_market.astimezone(user_tz)
        open_str = open_dt_local.strftime("%H:%M")
        close_str = close_dt_local.strftime("%H:%M")

        if event == "open":
            # Проверяем, совпадает ли локальное время пользователя с открытием биржи
            if now_local.hour == open_dt_local.hour and now_local.minute == open_dt_local.minute:
                lines.append(f"{market['emoji']} *{market['name']}* — {open_str}–{close_str}")
        elif event == "close_soon":
            # За 1 час до закрытия
            close_soon_dt_local = close_dt_local - timedelta(hours=1)
            if now_local.hour == close_soon_dt_local.hour and now_local.minute == close_soon_dt_local.minute:
                lines.append(f"{market['emoji']} *{market['name']}* — {close_str}")

    if lines:
        if event == "open":
            msg = (
                f"{' / '.join([l.split(' ')[0] + ' ' + l.split(' ')[1] for l in lines])} — открытие торгов!\n"
                f"🟢 Время работы бирж:\n" +
                "\n".join(lines) +
                f"\n(GMT{gmt_offset})\n"
                f"Удачных сделок! 🚀"
            )
            messages.append(msg)
        elif event == "close_soon":
            msg = (
                f"{' / '.join([l.split(' ')[0] + ' ' + l.split(' ')[1] for l in lines])} — до закрытия торгов остался 1 час!\n"
                f"🔔 Биржи закроются:\n" +
                "\n".join(lines) +
                f"\n(GMT{gmt_offset})\n"
                f"Проверьте свои позиции и заявки! ⏳"
            )
            messages.append(msg)
    return messages

# Пример использования:
# user_tz = pytz.timezone("Europe/Amsterdam")
# gmt_offset = "+2"
# messages = get_market_messages('open', user_tz, gmt_offset)
# for msg in messages:
#     print(msg)