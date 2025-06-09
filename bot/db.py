import asyncpg
import os
import ssl

DATABASE_URL = os.getenv("DATABASE_URL")

print("✅ asyncpg работает!")

async def connect_db():
    ssl_context = ssl.create_default_context()
    return await asyncpg.connect(DATABASE_URL, ssl=ssl_context)