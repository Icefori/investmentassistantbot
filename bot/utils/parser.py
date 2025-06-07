import json
import aiohttp
from datetime import datetime
import yfinance as yf
from bot.db import connect_db

PRICES_PATH = "data/prices.json"

# Получение цены с сайта KASE (асинхронно)
async def get_price_kase(ticker: str) -> float | None:
    try:
        now = int(datetime.now().timestamp())
        seven_days_ago = now - 7 * 86400
        one_day_ahead = now + 86400

        url = (
            f"https://old.kase.kz/charts/securities/history?"
            f"symbol=ALL:{ticker}&resolution=D"
            f"&from={seven_days_ago}&to={one_day_ahead}&chart_language_code=ru"
        )

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": f"https://old.kase.kz/ru/shares/show/{ticker}/"
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status != 200:
                  print(f"⚠️ Статус не 200 для {ticker}: {response.status}")
                return None
            text = await response.text()
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                print(f"⚠️ Не удалось распарсить JSON для {ticker}: {text[:100]}")
                return None

        closes = data.get("c", [])
        if not closes:
            return None

        return float(closes[-1])
    except Exception as ex:
        print(f"❌ Ошибка при получении цены с KASE для {ticker}: {ex}")
        return None

# Получение цены с Yahoo (синхронно)
def get_price_from_yahoo(ticker):
    try:
        data = yf.Ticker(ticker)
        hist = data.history(period="1d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as ex:
        print(f"❌ Ошибка при получении цены с Yahoo для {ticker}: {ex}")
        return None


# Обновление prices.json на основе данных из PostgreSQL
async def update_prices_json_from_portfolio():
    conn = await connect_db()
    records = await conn.fetch("SELECT ticker, category FROM portfolio")
    prices = {}

    for record in records:
        ticker = record["ticker"]
        category = record["category"]
        price = None

        try:
            if category == "KZ":
                price = await get_price_kase(ticker)
            else:
                price = get_price_from_yahoo(ticker)
        except Exception as ex:
            print(f"❌ Ошибка при получении цены для {ticker}: {ex}")
            price = None

        if price:
            prices[ticker] = round(price, 2)
        else:
            print(f"❌ Цена для {ticker} не найдена!")

    await conn.close()

    with open(PRICES_PATH, "w", encoding="utf-8") as f:
        json.dump(prices, f, indent=2, ensure_ascii=False)