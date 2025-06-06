import asyncpg
from datetime import datetime, date
from collections import defaultdict
from math import isclose
from bot.db import connect_db
from pathlib import Path

async def xirr(cash_flows):
    def npv(rate):
        return sum(cf / ((1 + rate) ** ((d - d0).days / 365)) for d, cf in cash_flows)

    d0 = min(d for d, _ in cash_flows)
    low, high = -0.999, 10.0
    for _ in range(100):
        mid = (low + high) / 2
        val = npv(mid)
        if isclose(val, 0, abs_tol=1e-6):
            return mid
        if val > 0:
            low = mid
        else:
            high = mid
    return None

async def summarize_portfolio():
    conn = await connect_db()
    portfolio_rows = await conn.fetch("SELECT * FROM portfolio")
    transactions_rows = await conn.fetch("SELECT * FROM transactions")
    await conn.close()

    if not portfolio_rows:
        return "❗ Портфель пуст. Добавьте хотя бы одну сделку."

    today = date.today()
    full_cash_flows = []
    full_market_value = 0
    category_totals = defaultdict(lambda: defaultdict(float))
    category_cashflows = defaultdict(list)
    ticker_data = {}
    tickers_by_category = defaultdict(list)

    prices_path = Path("data/prices.json")
    if not prices_path.exists():
        return "❗ Нет данных о ценах. Нажмите '📊 Мой портфель' чтобы обновить."

    import json
    with prices_path.open("r", encoding="utf-8") as f:
        prices = json.load(f)

    transactions_by_ticker = defaultdict(list)
    for row in transactions_rows:
        transactions_by_ticker[row["ticker"]].append(dict(row))

    for row in portfolio_rows:
        ticker = row["ticker"]
        category = row["category"]
        currency = row["currency"]
        transactions = transactions_by_ticker.get(ticker, [])

        if not transactions:
            continue

        total_qty = 0
        total_cost = 0.0
        earliest_date = None
        ticker_flows = []

        for tx in transactions:
            qty = tx["qty"]
            price = tx["price"]
            dt_str = tx["date"]
            dt = datetime.strptime(dt_str, "%d-%m-%Y").date()
            total_qty += qty
            total_cost += qty * price
            if qty > 0:
                ticker_flows.append((dt, -qty * price))
            if earliest_date is None or dt < earliest_date:
                earliest_date = dt

        if total_qty == 0:
            continue

        avg_price = total_cost / total_qty
        current_price = prices.get(ticker)
        if current_price is None:
            continue

        market_value = total_qty * current_price
        ticker_flows.append((today, market_value))
        full_cash_flows.extend(ticker_flows)
        full_market_value += market_value
        category_cashflows[category].extend(ticker_flows)

        ticker_data[ticker] = {
            "category": category,
            "currency": currency,
            "qty": total_qty,
            "avg_price": avg_price,
            "current_price": current_price,
            "total": market_value,
            "earliest": earliest_date,
            "cash_flows": ticker_flows
        }

        category_totals[category][currency] += market_value
        tickers_by_category[category].append(ticker)

    lines = ["📊 *Мой портфель*\n"]
    total_portfolio_value = sum(sum(v.values()) for v in category_totals.values())

    for category in sorted(tickers_by_category):
        for currency, total_sum in category_totals[category].items():
            category_percent = (total_sum / total_portfolio_value) * 100 if total_portfolio_value else 0
            xirr_result = await xirr(category_cashflows[category]) if category_cashflows[category] else None
            if xirr_result is not None:
                inflow = sum(cf for d, cf in category_cashflows[category] if cf > 0)
                outflow = -sum(cf for d, cf in category_cashflows[category] if cf < 0)
                net_gain = inflow - outflow
                gain_str = f"{net_gain:,.0f} ₸"
                xirr_str = f"📈 {xirr_result * 100:+.2f}% | {gain_str}"
            else:
                xirr_str = "📉 н/д"

            lines.append(f"*📁 {category}* — {total_sum:,.2f} {currency} ({category_percent:.1f}%) | {xirr_str}")

            sorted_tickers = sorted(
                tickers_by_category[category],
                key=lambda t: ticker_data[t]["total"],
                reverse=True
            )

            for ticker in sorted_tickers:
                t = ticker_data[ticker]
                percent = (t["total"] / total_sum) * 100 if total_sum else 0
                holding_days = (today - t["earliest"]).days if t["earliest"] else "?"
                gain = t["current_price"] - t["avg_price"]
                gain_sign = "📈" if gain >= 0 else "📉"
                gain_amount = gain * t["qty"]
                gain_percent = (gain / t["avg_price"]) * 100 if t["avg_price"] else 0

                lines.append(f"`{ticker}` — {t['qty']} шт | {t['total']:,.2f} {t['currency']} ({percent:.1f}%)")
                lines.append(f"{gain_sign} {gain_amount:,.0f} ({gain_percent:+.1f}%) за {holding_days} дн.")
            lines.append("")

    xirr_result = await xirr(full_cash_flows)
    if xirr_result is not None:
        inflow = sum(cf for d, cf in full_cash_flows if cf > 0)
        outflow = -sum(cf for d, cf in full_cash_flows if cf < 0)
        net_gain = inflow - outflow
        gain_str = f"{net_gain:,.0f} ₸"
        lines.append(f"📈 *Итог XIRR по портфелю:* {xirr_result * 100:+.2f}% | {gain_str}")
    else:
        lines.append("⚠️ *XIRR не удалось рассчитать.*")

    return "\n".join(lines)