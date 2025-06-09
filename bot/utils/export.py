import pandas as pd
import io
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

from bot.db import connect_db
from bot.utils.portfolio import summarize_portfolio

async def export_to_excel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    conn = await connect_db()
    portfolio = await conn.fetch("SELECT ticker, category, currency FROM portfolio")
    transactions = await conn.fetch("SELECT * FROM transactions ORDER BY date DESC")
    await conn.close()

    df_portfolio = pd.DataFrame(portfolio, columns=["ticker", "category", "currency"])
    df_transactions = pd.DataFrame(transactions, columns=["id", "ticker", "qty", "price", "date"])

    summary_text = await summarize_portfolio()
    summary_lines = summary_text.split("\n")
    df_summary = pd.DataFrame([line.strip("*") for line in summary_lines if line], columns=["Портфельная сводка"])

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df_portfolio.to_excel(writer, sheet_name="Портфель", index=False)
        df_transactions.to_excel(writer, sheet_name="Сделки", index=False)
        df_summary.to_excel(writer, sheet_name="Сводка", index=False)
    buffer.seek(0)

    await context.bot.send_document(
        chat_id=user.id,
        document=buffer,
        filename="portfolio_export.xlsx",
        caption="📁 Ваш портфельный отчёт"
    )
