import asyncio
from bot.utils.taxes import export_taxes_excel

if __name__ == "__main__":
    async def main():
        await export_taxes_excel(year=2024)
    asyncio.run(main())