import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime

TARGET_CURRENCIES = {"USD", "EUR", "RUB", "GBP", "CNY"}
CURRENCY_RSS_URL = "https://nationalbank.kz/rss/rates_all.xml"

async def fetch_exchange_rates():
    async with aiohttp.ClientSession() as session:
        async with session.get(CURRENCY_RSS_URL) as response:
            if response.status != 200:
                raise Exception(f"⚠️ Не удалось получить данные с сайта НБРК: {response.status}")
            xml_data = await response.text()

    root = ET.fromstring(xml_data)
    rates = []

    for item in root.findall("channel/item"):
        currency = item.find("title").text
        if currency not in TARGET_CURRENCIES:
            continue

        rate_info = {
            "currency": currency,
            "date": item.find("pubDate").text,
            "rate": float(item.find("description").text),
            "change": float(item.find("change").text),
            "index": item.find("index").text,
        }
        rates.append(rate_info)

    return rates

def format_currency_message(rates):
    today = datetime.now().strftime("%d.%m.%Y")
    message = f"💱 Курс валют на {today} (НБ РК):\n\n"
    for r in rates:
        arrow = "🔻" if r["index"] == "DOWN" else "🔺"
        message += f"*{r['currency']}*: {r['rate']} ₸ {arrow} ({r['change']} тг)\n"
    return message

