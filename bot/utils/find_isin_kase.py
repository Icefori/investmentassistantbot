import aiohttp
from bs4 import BeautifulSoup
import asyncio

async def get_isin_from_kase(ticker: str) -> str:
    """
    Получает ISIN для тикера с сайта old.kase.kz.
    Возвращает первые 2 буквы ISIN (страну) или пустую строку.
    """
    url = f"https://old.kase.kz/ru/shares/show/{ticker}/"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                print(f"HTTP status: {resp.status}")
                return ""
            html = await resp.text()
    soup = BeautifulSoup(html, "html.parser")
    info_table = soup.find("div", class_="info-table")
    if info_table:
        cells = info_table.find_all("div", class_="info-table__cell")
        for i, cell in enumerate(cells):
            key = cell.text.strip().upper().replace(" ", "")
            if key.startswith("ISIN"):
                if i + 1 < len(cells):
                    value = cells[i + 1].text.strip()
                    print(f"==> Найден ISIN: {value}")
                    return value[:2]  # Возвращаем только первые 2 буквы
    print("ISIN не найден в info-table. Проверьте структуру страницы или тикер.")
    return ""

if __name__ == "__main__":
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else "HSBK"
    print(f"🔎 Ищу ISIN для тикера: {ticker}")
    async def main():
        country_code = await get_isin_from_kase(ticker)
        if country_code:
            print(f"✅ Первые 2 буквы ISIN: {country_code}")
        else:
            print("❌ ISIN не найден")
    asyncio.run(main())