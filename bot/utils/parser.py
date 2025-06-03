
import json
import os
import time
import requests
from datetime import datetime, timedelta
import yfinance as yf

PORTFOLIO_PATH = "data/portfolio.json"
PRICES_PATH = "data/prices.json"

# Получение цены с сайта KASE
def get_price_kase(ticker: str) -> float | None:
    try:
        print(f"🌐 Обращаемся к old.kase.kz для тикера: {ticker}")

        now = int(time.time())
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
        print(f"🔗 URL: {url}")
        print(f"📶 Статус ответа: {response.status_code}")

        if response.status_code != 200:
            print("❌ Не удалось получить данные.")
            return None

        data = response.json()
        closes = data.get("c", [])
        if not closes:
            print("⚠️ История пуста, цен нет.")
            return None

        price = closes[-1]
        print(f"✅ Получена цена закрытия: {price}")
        return float(price)

    except Exception as e:
        print(f"🔥 Ошибка запроса: {e}")
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

# Обновление цен по тикерам из portfolio.json
def update_prices_json_from_portfolio():
    if not os.path.exists(PORTFOLIO_PATH):
        print("❌ Portfolio file not found.")
        return

    with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
        portfolio = json.load(f)

    prices = {}

    for ticker, data in portfolio.items():
        category = data.get("category", "")
        price = None

        print(f"🔍 Обновляем: {ticker} (категория: {category})")

        if category == "KZ":
            price = get_price_kase(ticker)
        else:
            price = get_price_from_yahoo(ticker)

        if price:
            prices[ticker] = round(price, 2)
            print(f"✅ {ticker} = {prices[ticker]}")
        else:
            print(f"⚠️ Не удалось обновить цену: {ticker}")

    with open(PRICES_PATH, "w", encoding="utf-8") as f:
        json.dump(prices, f, indent=2, ensure_ascii=False)
