import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

TARGET_CURRENCIES = {"USD", "EUR", "RUB", "GBP", "CNY"}
CURRENCY_RSS_DATE_URL = "https://nationalbank.kz/rss/get_rates.cfm?fdate={date}"

async def fetch_rates_by_date(date: datetime):
    url = CURRENCY_RSS_DATE_URL.format(date=date.strftime("%d.%m.%Y"))
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise Exception(f"⚠️ Не удалось получить данные с сайта НБРК: {response.status}")
            xml_data = await response.text()
    root = ET.fromstring(xml_data)
    rates = {}
    changes = {}
    for item in root.findall("channel/item"):
        currency = item.find("title").text
        if currency not in TARGET_CURRENCIES:
            continue
        rate = float(item.find("description").text)
        change = float(item.find("change").text)
        rates[currency] = rate
        changes[currency] = change
    print(f"[DEBUG] {date.strftime('%d.%m.%Y')} rates: {rates}")  # Для отладки
    return rates, changes

async def fetch_exchange_rates_full():
    today = datetime.now()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    today_rates, today_changes = await fetch_rates_by_date(today)
    week_rates, _ = await fetch_rates_by_date(week_ago)
    month_rates, _ = await fetch_rates_by_date(month_ago)

    return today_rates, today_changes, week_rates, month_rates

def format_currency_message_structured(today_rates, today_changes, week_rates, month_rates):
    today = datetime.now().strftime("%d.%m.%Y")
    header = (
        f"💱 Курс валют на {today} (НБ РК)\n"
        f"{'Валюта':<6} {'Текущий':>10} {'День':>10} {'7д':>10} {'30д':>10}\n"
        f"{'':<6} {'курс':>10} {'%':>10} {'%':>10} {'%':>10}\n"
        f"{'-'*50}"
    )
    lines = [header]
    found = False
    for cur in sorted(TARGET_CURRENCIES):
        cur_rate = today_rates.get(cur)
        day_change = today_changes.get(cur)
        week_rate = week_rates.get(cur)
        month_rate = month_rates.get(cur)
        if not cur_rate or week_rate is None or month_rate is None or day_change is None:
            continue

        found = True
        # Изменение за день в процентах (по формуле: change / (rate - change) * 100)
        prev_day_rate = cur_rate - day_change if cur_rate - day_change != 0 else 1
        day_delta = (day_change / prev_day_rate) * 100

        week_delta = ((cur_rate - week_rate) / week_rate * 100) if week_rate else 0
        month_delta = ((cur_rate - month_rate) / month_rate * 100) if month_rate else 0

        def arrow(val):
            if val > 0.05:
                return "🔺"
            elif val < -0.05:
                return "🔻"
            else:
                return "⏺"

        lines.append(
            f"{cur:<6} {cur_rate:>10.2f} "
            f"{arrow(day_delta)}{day_delta:>8.2f}% "
            f"{arrow(week_delta)}{week_delta:>8.2f}% "
            f"{arrow(month_delta)}{month_delta:>8.2f}%"
        )
    if not found:
        lines.append("Нет данных по курсам валют.")
    return "\n".join(lines)

# Пример асинхронного использования:
# today_rates, today_changes, week_rates, month_rates = await fetch_exchange_rates_full()
# message = format_currency_message_structured(today_rates, today_changes, week_rates, month_rates)

