import asyncpg
import os
import ssl

DATABASE_URL = os.getenv("DATABASE_URL")

print("✅ asyncpg работает!")

async def connect_db():
    ssl_context = ssl.create_default_context()
    return await asyncpg.connect(DATABASE_URL, ssl=ssl_context)

async def init_db():
    conn = await connect_db()
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id SERIAL PRIMARY KEY,
            ticker TEXT NOT NULL,
            quantity NUMERIC NOT NULL,
            price NUMERIC NOT NULL,
            currency TEXT NOT NULL,
            date TEXT NOT NULL
        );
    """)
    await conn.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(init_db())
