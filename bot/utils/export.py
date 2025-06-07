import pandas as pd
from io import BytesIO
from telegram import InputFile, Update
from telegram.ext import ContextTypes
from bot.db import connect_db
from bot.utils.portfolio import summarize_portfolio

async def export_to_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = await connect_db()

    df_portfolio = pd.DataFrame(await conn.fetch("SELECT * FROM portfolio"))
    df_transactions = pd.DataFrame(await conn.fetch("SELECT * FROM transactions"))
    summary = await summarize_portfolio()
    df_summary = pd.DataFrame(summary.splitlines(), columns=["Итог"])

    await conn.close()

    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df_portfolio.to_excel(writer, sheet_name="Портфель", index=False)
        df_transactions.to_excel(writer, sheet_name="Сделки", index=False)
        df_summary.to_excel(writer, sheet_name="Сводка", index=False)

    buffer.seek(0)
    await update.message.reply_document(
        document=InputFile(buffer, filename="portfolio_export.xlsx"),
        caption="📤 Готово! Скачай Excel файл"
    )
