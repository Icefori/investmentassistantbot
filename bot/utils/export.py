import logging
import pandas as pd
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from bot.db import connect_db
from bot.utils.parser import get_price_kase, get_price_from_yahoo
from bot.scheduler.currency import fetch_rates_by_date

logger = logging.getLogger(__name__)

async def export_to_excel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id

    try:
        conn = await connect_db()
        # Получаем все нужные поля кроме user_id
        portfolio = await conn.fetch(
            "SELECT ticker, category, currency FROM portfolio WHERE user_id = $1", user_id
        )
        transactions = await conn.fetch(
            "SELECT id, ticker, qty, price, date, exchange, cp_fee, br_fee, ex_fee, sum, end_pr FROM transactions WHERE user_id = $1 ORDER BY date DESC",
            user_id
        )
        await conn.close()

        if not portfolio:
            await update.message.reply_text("Ваш портфель пуст. Нет данных для экспорта.")
            logger.info(f"User {user_id} tried to export empty portfolio.")
            return

        # Преобразуем в DataFrame
        df_portfolio = pd.DataFrame(portfolio, columns=["ticker", "category", "currency"])
        df_transactions = pd.DataFrame(transactions, columns=[
            "id", "ticker", "qty", "price", "date", "exchange", "cp_fee", "br_fee", "ex_fee", "sum", "end_pr"
        ])

        # Добавляем колонку "Курс USD" на дату сделки
        usd_rates = []
        sum_usd = []
        for idx, row in df_transactions.iterrows():
            try:
                # Получаем курс USD на дату сделки
                date_obj = datetime.strptime(row["date"], "%d-%m-%Y")
                rates, _ = await fetch_rates_by_date(date_obj)
                rates_dict = dict(rates)
                usd_rate = rates_dict.get("USD", None)
                usd_rates.append(usd_rate)
                # Переводим sum в USD если актив в KZT, иначе оставляем как есть
                if usd_rate and row["sum"] is not None:
                    if row["exchange"] == "KZT":
                        sum_usd.append(round(float(row["sum"]) / usd_rate, 2))
                    elif row["exchange"] == "USD":
                        sum_usd.append(float(row["sum"]))
                    else:
                        sum_usd.append(None)
                else:
                    sum_usd.append(None)
            except Exception as e:
                logger.error(f"Ошибка получения курса USD на дату {row['date']}: {e}")
                usd_rates.append(None)
                sum_usd.append(None)
        df_transactions["Курс USD"] = usd_rates
        df_transactions["Сумма в USD"] = sum_usd

        # Итоговые значения по сделкам (инвестировано)
        total_invested_kzt = 0.0
        total_invested_usd = 0.0
        for idx, row in df_transactions.iterrows():
            if row["exchange"] == "KZT" and row["sum"] is not None:
                total_invested_kzt += float(row["sum"])
            elif row["exchange"] == "USD" and row["sum"] is not None:
                total_invested_usd += float(row["sum"])

        # Группировка по тикеру для сводки
        df_grouped = df_transactions.groupby("ticker").agg({
            "qty": "sum",
            "price": "mean"
        }).reset_index()
        df_grouped.rename(columns={"qty": "Количество", "price": "Средняя цена"}, inplace=True)

        # Добавляем текущую цену и прибыль
        tickers = df_grouped["ticker"].tolist()
        current_prices = []
        for ticker in tickers:
            try:
                price = await get_price_kase(ticker)
                if price is None:
                    price = await get_price_from_yahoo(ticker)
                current_prices.append(price if price is not None else 0)
            except Exception as e:
                logger.error(f"Ошибка получения цены для {ticker}: {e}")
                current_prices.append(0)
        df_grouped["Текущая цена"] = current_prices
        df_grouped["Инвестировано"] = (df_grouped["Средняя цена"] * df_grouped["Количество"]).round(2)
        df_grouped["Текущая стоимость"] = (df_grouped["Текущая цена"] * df_grouped["Количество"]).round(2)
        df_grouped["Δ₸"] = (df_grouped["Текущая стоимость"] - df_grouped["Инвестировано"]).round(2)
        df_grouped["Δ%"] = df_grouped.apply(
            lambda row: round((row["Δ₸"] / row["Инвестировано"] * 100), 2) if row["Инвестировано"] else 0, axis=1
        )

        # Формируем Excel-файл
        from io import BytesIO
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_portfolio.to_excel(writer, sheet_name="Портфель", index=False)
            df_transactions.to_excel(writer, sheet_name="Сделки", index=False)
            df_grouped.to_excel(writer, sheet_name="Сводка", index=False)
            # Итоговые значения на отдельном листе
            summary = pd.DataFrame({
                "Всего инвестировано, ₸": [round(total_invested_kzt, 2)],
                "Всего инвестировано, $": [round(total_invested_usd, 2)]
            })
            summary.to_excel(writer, sheet_name="Итоги", index=False)
        output.seek(0)

        await update.message.reply_document(
            document=output,
            filename=f"portfolio_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            caption="Ваш портфель успешно экспортирован в Excel!"
        )
        logger.info(f"User {user_id} exported portfolio to Excel.")
    except Exception as e:
        logger.exception(f"Ошибка экспорта портфеля для user_id={user_id}: {e}")
        await update.message.reply_text("Произошла ошибка при экспорте портфеля. Попробуйте ещё раз позже.")
