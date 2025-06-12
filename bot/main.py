import asyncio
from .app import run_bot
  # функция, которая запускает вашего Telegram-бота
from .scheduler.scheduler import run_scheduler  # функция, которая запускает планировщик

async def main():
    bot_task = asyncio.create_task(run_bot())
    scheduler_task = asyncio.create_task(run_scheduler())
    await asyncio.gather(bot_task, scheduler_task)

if __name__ == "__main__":
    asyncio.run(main())