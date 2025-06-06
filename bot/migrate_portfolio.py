import json
import asyncio
from db import connect_db

PORTFOLIO_PATH = "data/portfolio.json"

async def migrate():
    # Шаг 1: Подключение к базе
    conn = await connect_db()

    # Шаг 2: Чтение портфеля
    with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
        portfolio = json.load(f)

    # Шаг 3: Очистка таблицы (опционально)
    await conn.execute("DELETE FROM deals;")

    # Шаг 4: Добавление всех сделок
    for ticker, data in portfolio.items():
        currency = data["currency"]
        for tx in data.get("transactions", []):
            await conn.execute("""
                INSERT INTO deals (ticker, quantity, price, currency, date)
                VALUES ($1, $2, $3, $4, $5);
            """, ticker, tx["qty"], tx["price"], currency, tx["date"])

    await conn.close()
    print("✅ Данные успешно мигрированы в базу.")

if __name__ == "__main__":
    asyncio.run(migrate())
