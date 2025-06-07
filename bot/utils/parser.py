
import json
import requests
import asyncpg
from datetime import datetime
import yfinance as yf
from bot.db import connect_db

PRICES_PATH = "data/prices.json"

# Получение цены с сайта KASE
def get_price_kase(ticker: str) -> float | None:
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

        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None

        data = response.json()
        closes = data.get("c", [])
        if not closes:
            return None

        return float(closes[-1])

    except Exception:
        return None

# Получение цены с Yahoo
def get_price_from_yahoo(ticker):
    try:
        data = yf.Ticker(ticker)
        hist = data.history(period="1d")
        if hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except:
        return None

# Обновление цен по тикерам из БД
async def update_prices_json_from_portfolio():
    conn = await connect_db()
    records = await conn.fetch("SELECT ticker, category FROM portfolio")
    prices = {}

    for record in records:
        ticker = record["ticker"]
        category = record["category"]
        price = None

        if category == "KZ":
            price = await get_price_kase(ticker)
        else:
            price = await get_price_from_yahoo(ticker)

        if price:
            prices[ticker] = round(price, 2)
        if not price:
            print(f"❌ Цена для {ticker} не найдена!")
        
    
    await conn.close()

    with open(PRICES_PATH, "w", encoding="utf-8") as f:
        json.dump(prices, f, indent=2, ensure_ascii=False)
