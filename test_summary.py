import asyncio
from bot.utils.portfolio import summarize_portfolio

async def main():
    summary = await summarize_portfolio()
    print(summary)

if __name__ == "__main__":
    asyncio.run(main())

