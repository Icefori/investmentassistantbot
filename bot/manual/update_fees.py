import asyncio
from bot.db import connect_db
from bot.utils.fees import calc_fees

async def update_missing_fees():
    conn = await connect_db()
    rows = await conn.fetch("SELECT id, exchange, qty, price, br_fee, ex_fee, cp_fee FROM transactions WHERE sum IS NULL OR end_pr IS NULL")
    for row in rows:
        exchange = row["exchange"]
        qty = abs(row["qty"])
        price = row["price"]
        is_sell = row["qty"] < 0
        fees = calc_fees(exchange, qty, price, is_sell)
        await conn.execute(
            """
            UPDATE transactions
            SET br_fee = $1, ex_fee = $2, cp_fee = $3, sum = $4, end_pr = $5
            WHERE id = $6
            """,
            fees["br_fee"], fees["ex_fee"], fees["cp_fee"], fees["sum"], fees["end_pr"], row["id"]
        )
    await conn.close()
    print("✅ Все пустые sum и end_pr обновлены.")

if __name__ == "__main__":
    asyncio.run(update_missing_fees())