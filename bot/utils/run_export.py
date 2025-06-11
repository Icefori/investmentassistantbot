import sys
import asyncio
from bot.utils.taxes import export_taxes_excel

if __name__ == "__main__":
    year = 2024  # значение по умолчанию
    if len(sys.argv) > 1:
        try:
            year = int(sys.argv[1])
        except Exception:
            print("Укажите год числом, например: python -m bot.utils.run_export 2025")
            sys.exit(1)
    async def main():
        await export_taxes_excel(year=year)
    asyncio.run(main())