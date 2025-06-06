import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.db import connect_db
import json
import asyncio

PORTFOLIO_PATH = "data/portfolio.json"

async def migrate():
    conn = await connect_db()

    # Пример создания таблицы
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS portfolio (
        ticker TEXT PRIMARY KEY,
        category TEXT,
        currency TEXT
    );
    """)

    await conn.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id SERIAL PRIMARY KEY,
        ticker TEXT REFERENCES portfolio(ticker),
        qty INT,
        price FLOAT,
        date TEXT
    );
    """)

    with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    for ticker, details in data.items():
        await conn.execute("INSERT INTO portfolio (ticker, category, currency) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING", 
            ticker, details["category"], details["currency"])

        for tx in details["transactions"]:
            await conn.execute("INSERT INTO transactions (ticker, qty, price, date) VALUES ($1, $2, $3, $4)", 
                ticker, tx["qty"], tx["price"], tx["date"])

    print("✅ Данные перенесены в PostgreSQL")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(migrate())
