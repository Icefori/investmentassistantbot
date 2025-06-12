import asyncpg
from datetime import datetime, date
from collections import defaultdict
from math import isclose
from bot.db import connect_db
from bot.scheduler.currency import fetch_rates_by_date

async def xirr(cash_flows: list[tuple[datetime, float]]) -> float | None:
    if not cash_flows:
        return None

    d0 = min(d for d, _ in cash_flows)

    def npv(rate):
        return sum(cf / ((1 + rate) ** ((d - d0).days / 365)) for d, cf in cash_flows)

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
    full_market_value_kzt = 0
    full_market_value_usd = 0
    category_totals_kzt = defaultdict(float)
    category_totals_usd = defaultdict(float)
    ticker_data = {}
    category_cashflows = defaultdict(list)
    tickers_by_category = defaultdict(list)
    missing_currencies = set()

    # Получаем только курсы за сегодня
    today_rates, _ = await fetch_rates_by_date(datetime.now())
    exchange_rates = dict(today_rates)
    exchange_rates["KZT"] = 1.0
    exchange_rates["USD"] = exchange_rates.get("USD", 1.0)

    get_rate = lambda cur: (exchange_rates.get(cur) or 1.0)

    transactions_by_ticker = defaultdict(list)
    for tx in transactions_rows:
        transactions_by_ticker[tx["ticker"]].append(dict(tx))

    from bot.utils.parser import get_price_kase, get_price_from_yahoo

    for row in portfolio_rows:
        ticker = row["ticker"]
        category = row["category"]
        currency = row["currency"]
        txs = transactions_by_ticker.get(ticker, [])
        if not txs:
            continue

        # Проверка наличия курса валюты
        if currency not in exchange_rates:
            missing_currencies.add(currency)

        total_qty = 0
        total_cost = 0.0
        earliest_date = None
        ticker_flows = []

        for tx in txs:
            qty = tx["qty"]
            price = tx["price"]
            dt = datetime.strptime(tx["date"], "%d-%m-%Y").date()
            total_qty += qty
            total_cost += qty * price
            if qty > 0:
                ticker_flows.append((dt, -qty * price))
            if earliest_date is None or dt < earliest_date:
                earliest_date = dt

        if total_qty == 0:
            continue

        avg_price = total_cost / total_qty

        # Получаем цену
        if currency == "KZT":
            current_price = await get_price_kase(ticker)
        else:
            current_price = await get_price_from_yahoo(ticker)
            if current_price is None:
                current_price = await get_price_kase(ticker)

        if current_price is None:
            continue

        market_value = total_qty * current_price

        # Конвертация в обе валюты
        if currency == "KZT":
            market_value_kzt = market_value
            market_value_usd = market_value / get_rate("USD")
        elif currency == "USD":
            market_value_usd = market_value
            market_value_kzt = market_value * get_rate("USD")
        else:
            # Для других валют: сначала в тенге, потом в доллары
            market_value_kzt = market_value * get_rate(currency)
            market_value_usd = market_value_kzt / get_rate("USD")

        ticker_flows.append((today, market_value_kzt))
        full_cash_flows.extend(ticker_flows)

        full_market_value_kzt += market_value_kzt
        full_market_value_usd += market_value_usd
        category_totals_kzt[category] += market_value_kzt
        category_totals_usd[category] += market_value_usd
        category_cashflows[category].extend(ticker_flows)

        ticker_data[ticker] = {
            "category": category,
            "currency": currency,
            "qty": total_qty,
            "avg_price": avg_price,
            "current_price": current_price,
            "total": market_value,
            "total_kzt": market_value_kzt,
            "total_usd": market_value_usd,
            "earliest": earliest_date,
        }

        tickers_by_category[category].append(ticker)

    lines = ["📊 *Мой портфель*\n"]

    # Сообщение о пропущенных валютах
    filtered_missing = {cur for cur in missing_currencies if cur not in ("KZT", "USD")}
    if filtered_missing:
        lines.append(
            "⚠️ *Внимание!* Нет курса для валют: " +
            ", ".join(f"`{cur}`" for cur in sorted(filtered_missing)) +
            ". Суммы по этим активам могут быть некорректны."
        )

    for category in sorted(tickers_by_category):
        category_total_kzt = category_totals_kzt[category]
        category_total_usd = category_totals_usd[category]
        category_percent = (category_total_kzt / full_market_value_kzt) * 100 if full_market_value_kzt else 0

        # XIRR и прирост по категории
        xirr_result = await xirr(category_cashflows[category])
        inflow = sum(cf for d, cf in category_cashflows[category] if cf > 0)
        outflow = -sum(cf for d, cf in category_cashflows[category] if cf < 0)
        net_gain = inflow - outflow
        gain_percent = (net_gain / outflow * 100) if outflow else 0

        # Формат вывода по категории
        lines.append(f"📁 {category} - {category_percent:.1f}%")
        lines.append(f"{category_total_kzt:,.2f} ₸ | {category_total_usd:,.2f} $ | " +
                     (f"📈 {xirr_result * 100:+.2f}%" if xirr_result else f"📉 {gain_percent:+.2f}%"))

        for ticker in sorted(tickers_by_category[category], key=lambda t: ticker_data[t]["total_kzt"], reverse=True):
            t = ticker_data[ticker]
            percent = (t["total_kzt"] / category_total_kzt) * 100 if category_total_kzt else 0
            holding_days = (today - t["earliest"]).days if t["earliest"] else "?"
            gain = t["current_price"] - t["avg_price"]
            gain_sign = "📈" if gain >= 0 else "📉"
            gain_amount = gain * t["qty"]
            gain_percent_ticker = (gain / t["avg_price"]) * 100 if t["avg_price"] else 0

            # Красивое выравнивание по валютам
            value_str = f"{t['total_kzt']:,.2f} ₸ | {t['total_usd']:,.2f} $"

            lines.append(
                f"`{ticker}` — {percent:.1f}%"
            )
            lines.append(
                f"{t['qty']} шт | {value_str}"
            )
            lines.append(
                f"{gain_sign} {gain_amount:,.0f} ({gain_percent_ticker:+.1f}%) за {holding_days} дн."
            )
            lines.append("")  # пустая строка между активами

    if full_cash_flows:
        xirr_result = await xirr(full_cash_flows)
        inflow = sum(cf for d, cf in full_cash_flows if cf > 0)
        outflow = -sum(cf for d, cf in full_cash_flows if cf < 0)
        net_gain = inflow - outflow
        gain_str = f"{net_gain:,.0f} ₸"
        gain_str_usd = f"{net_gain / get_rate('USD'):,.0f} $"
        xirr_str = f"{xirr_result * 100:+.2f}%" if xirr_result else "н/д"
        lines.append(
            f"📈 *Итог XIRR по портфелю:* {xirr_str} | {gain_str} | {gain_str_usd}"
        )
        lines.append(
            f"*Общая стоимость портфеля:* {full_market_value_kzt:,.2f} ₸ | {full_market_value_usd:,.2f} $"
        )
    else:
        lines.append("⚠️ *Недостаточно данных для расчета XIRR.*")

    return "\n".join(lines)