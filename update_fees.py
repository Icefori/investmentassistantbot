import asyncio
from bot.db import connect_db
from bot.utils.fees import calc_fees

async def update_all_fees():
    conn = await connect_db()
    rows = await conn.fetch("SELECT id, exchange, qty, price, type FROM transactions")
    for row in rows:
        exchange = row["exchange"]
        qty = row["qty"]
        price = row["price"]
        is_sell = (row["type"].lower() == "sell")  # или как у вас обозначается продажа
        fees = calc_fees(exchange, qty, price, is_sell)
        await conn.execute(
            """
            UPDATE transactions
            SET br_fee = $1, ex_fee = $2, cp_fee = $3
            WHERE id = $4
            """,
            fees["br_fee"], fees["ex_fee"], fees["cp_fee"], row["id"]
        )
    await conn.close()
    print("✅ Комиссии обновлены для всех сделок.")

if __name__ == "__main__":
    asyncio.run(update_all_fees())