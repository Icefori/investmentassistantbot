import json
import aiohttp
from datetime import datetime
import yfinance as yf
import asyncio
from bot.db import connect_db

# Get price from KASE (async)
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
                text = await response.text()
                data = json.loads(text)
                closes = data.get("c", [])
                if not closes:
                    print(f"⚠️ No price data for {ticker}")
                    return None
                return float(closes[-1])

    except Exception as ex:
        print(f"❌ Error fetching KASE price for {ticker}: {ex}")
        return None

# Get price from Yahoo (async via executor)
async def get_price_from_yahoo(ticker: str) -> float | None:
    loop = asyncio.get_running_loop()
    def fetch():
        try:
            data = yf.Ticker(ticker)
            hist = data.history(period="1d")
            if hist.empty:
                return None
            return float(hist["Close"].iloc[-1])
        except Exception as ex:
            print(f"❌ Error fetching Yahoo price for {ticker}: {ex}")
            return None
    return await loop.run_in_executor(None, fetch)