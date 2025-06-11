import yfinance as yf
import asyncio

async def get_isin_from_yahoo(ticker: str) -> str:
    """
    Получает ISIN для тикера через yfinance.
    Возвращает ISIN или пустую строку, если не найден.
    """
    loop = asyncio.get_running_loop()
    def fetch():
        try:
            data = yf.Ticker(ticker)
            isin = getattr(data, "isin", None)
            if isin:
                return isin
            # Иногда isin лежит в data.info
            info = getattr(data, "info", {})
            return info.get("isin", "")
        except Exception as ex:
            print(f"Ошибка при поиске ISIN через yfinance: {ex}")
            return ""
    return await loop.run_in_executor(None, fetch)

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Укажите тикер: python find_isin.yahoo.py <TICKER>")
        sys.exit(1)
    ticker = sys.argv[1]
    print(f"🔎 Ищу ISIN для тикера: {ticker} (Yahoo)")
    async def main():
        isin = await get_isin_from_yahoo(ticker)
        if isin:
            print(f"✅ ISIN найден: {isin}")
            print(f"Первые 2 буквы ISIN: {isin[:2]}")
        else:
            print("❌ ISIN не найден")
    asyncio.run(main())