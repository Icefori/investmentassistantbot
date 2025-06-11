import asyncpg
import os
import ssl
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

print("✅ asyncpg работает!")
print(f"DATABASE_URL: {'[HIDDEN]' if DATABASE_URL else '[NOT SET]'}")

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL не задан! Проверьте .env файл и переменные окружения.")

async def connect_db():
    # Для Heroku и Amazon RDS всегда используем SSL по умолчанию
    ssl_context = ssl.create_default_context()
    return await asyncpg.connect(DATABASE_URL, ssl=ssl_context)