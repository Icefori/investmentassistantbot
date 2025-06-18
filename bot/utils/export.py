import pandas as pd
import io
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

from bot.db import connect_db
from bot.utils.parser import get_price_kase, get_price_from_yahoo

async def export_to_excel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id

    conn = await connect_db()
    # Фильтруем только по user_id
    portfolio = await conn.fetch("SELECT ticker, category, currency FROM portfolio WHERE user_id = $1", user_id)
    transactions = await conn.fetch("SELECT * FROM transactions WHERE user_id = $1 ORDER BY date DESC", user_id)
    await conn.close()

    df_portfolio = pd.DataFrame(portfolio, columns=["ticker", "category", "currency"])
    df_transactions = pd.DataFrame(transactions, columns=["id", "ticker", "qty", "price", "date"])

    # Группировка транзакций
    df_grouped = df_transactions.groupby("ticker").agg({"qty": "sum", "price": "mean"}).reset_index()
    df_grouped.rename(columns={"qty": "Кол-во", "price": "Средняя цена"}, inplace=True)

    tickers = df_grouped["ticker"].tolist()
    latest_prices = []
    for ticker in tickers:
        price = await get_price_kase(ticker)
        if price is None:
            price = await get_price_from_yahoo(ticker)
        latest_prices.append(round(price or 0, 2))

    df_grouped["Цена"] = latest_prices
    df_grouped["Общая"] = (df_grouped["Кол-во"] * df_grouped["Цена"]).round(2)
    df_grouped["Инвестировано"] = (df_grouped["Кол-во"] * df_grouped["Средняя цена"]).round(2)
    df_grouped["Δ₸"] = (df_grouped["Общая"] - df_grouped["Инвестировано"]).round(2)
    df_grouped["Δ%"] = ((df_grouped["Δ₸"] / df_grouped["Инвестировано"]) * 100).round(2)

    total_value = df_grouped["Общая"].sum()
    df_grouped["% от портфеля"] = ((df_grouped["Общая"] / total_value) * 100).round(2) if total_value else 0

    df_summary = df_grouped[
        ["ticker", "Кол-во", "Цена", "Общая", "% от портфеля", "Δ%", "Δ₸"]
    ].rename(columns={"ticker": "Ticker"})

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
