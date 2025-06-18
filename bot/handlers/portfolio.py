import asyncpg
from datetime import datetime, date
from collections import defaultdict, deque
from bot.db import connect_db
from bot.scheduler.currency import fetch_rates_by_date

async def summarize_portfolio(update, context):
    """
    📊 *Мой портфель*

    В этом отчёте показана **нереализованная прибыль** по каждому активу, категории и всему портфелю.
    Формула: (Текущая стоимость - Сумма вложений) / Сумма вложений × 100%
    Вложения считаются по курсу на дату покупки. Если были продажи, вложения уменьшаются по принципу FIFO.
    Дивиденды, комиссии и реализованная прибыль не учитываются.
    """

    user_id = update.effective_user.id  # Получаем user_id пользователя

    conn = await connect_db()
    portfolio_rows = await conn.fetch("SELECT * FROM portfolio WHERE user_id = $1", user_id)
    transactions_rows = await conn.fetch("SELECT * FROM transactions WHERE user_id = $1 ORDER BY date", user_id)
    await conn.close()

    if not portfolio_rows:
        return (
            "❗ Портфель пуст. Добавьте хотя бы одну сделку.\n\n"
            "ℹ️ В этом отчёте отображается *нереализованная прибыль* по формуле:\n"
            "(Текущая стоимость - Сумма вложений) / Сумма вложений × 100%\n"
            "Вложения считаются по курсу на дату покупки, продажи уменьшают вложения по FIFO."
        )

    today = date.today()
    ticker_data = {}
    tickers_by_category = defaultdict(list)
    category_invested = defaultdict(float)
    category_gain = defaultdict(float)
    category_market_value_kzt = defaultdict(float)
    category_market_value_usd = defaultdict(float)
    full_invested = 0.0
    full_gain = 0.0
    full_market_value_kzt = 0.0
    full_market_value_usd = 0.0

    # Получаем курсы валют на все даты, которые есть в транзакциях
    all_dates = sorted({datetime.strptime(tx["date"], "%d-%m-%Y").date() for tx in transactions_rows})
    rates_by_date = {}
    for d in all_dates:
        rates, _ = await fetch_rates_by_date(datetime.combine(d, datetime.min.time()))
        rates_by_date[d] = dict(rates)
        rates_by_date[d]["KZT"] = 1.0
        rates_by_date[d]["USD"] = rates_by_date[d].get("USD", 1.0)

    # Курс на сегодня
    today_rates, _ = await fetch_rates_by_date(datetime.now())
    exchange_rates = dict(today_rates)
    exchange_rates["KZT"] = 1.0
    exchange_rates["USD"] = exchange_rates.get("USD", 1.0)
    get_rate_today = lambda cur: (exchange_rates.get(cur) or 1.0)

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

        # FIFO очередь: каждый элемент — (qty, price, date, currency, rate_on_date)
        fifo = deque()
        total_qty = 0

        for tx in txs:
            qty = tx["qty"]
            price = tx["price"]
            tx_date = datetime.strptime(tx["date"], "%d-%m-%Y").date()
            rate_on_date = rates_by_date[tx_date].get(currency, 1.0)
            if qty > 0:
                # Покупка — добавляем в FIFO
                fifo.append({"qty": qty, "price": price, "rate": rate_on_date, "currency": currency})
                total_qty += qty
            elif qty < 0:
                # Продажа — снимаем с FIFO (FIFO-вычитание)
                sell_qty = -qty
                total_qty += qty
                while sell_qty > 0 and fifo:
                    lot = fifo[0]
                    if lot["qty"] > sell_qty:
                        lot["qty"] -= sell_qty
                        sell_qty = 0
                    else:
                        sell_qty -= lot["qty"]
                        fifo.popleft()

        if total_qty <= 0 or not fifo:
            continue

        # Считаем вложения по FIFO-остатку
        invested = 0.0
        for lot in fifo:
            if lot["currency"] == "KZT":
                invested += lot["price"] * lot["qty"]
            elif lot["currency"] == "USD":
                invested += lot["price"] * lot["qty"] * lot["rate"]
            else:
                invested += lot["price"] * lot["qty"] * lot["rate"]

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
            market_value_usd = market_value / get_rate_today("USD")
        elif currency == "USD":
            market_value_usd = market_value
            market_value_kzt = market_value * get_rate_today("USD")
        else:
            market_value_kzt = market_value * get_rate_today(currency)
            market_value_usd = market_value_kzt / get_rate_today("USD")

        # Чистая прибыль и проценты по активу
        gain = market_value_kzt - invested
        gain_percent = (gain / invested * 100) if invested else 0

        ticker_data[ticker] = {
            "category": category,
            "currency": currency,
            "qty": total_qty,
            "invested": invested,
            "current_price": current_price,
            "market_value": market_value,
            "market_value_kzt": market_value_kzt,
            "market_value_usd": market_value_usd,
            "gain": gain,
            "gain_percent": gain_percent,
        }

        tickers_by_category[category].append(ticker)
        category_invested[category] += invested
        category_gain[category] += gain
        category_market_value_kzt[category] += market_value_kzt
        category_market_value_usd[category] += market_value_usd
        full_invested += invested
        full_gain += gain
        full_market_value_kzt += market_value_kzt
        full_market_value_usd += market_value_usd

    lines = [
        "📊 *Мой портфель*\n",
        "ℹ️ В этом отчёте отображается *нереализованная прибыль* по формуле:\n"
        "(Текущая стоимость - Сумма вложений) / Сумма вложений × 100%\n"
        "Вложения считаются по курсу на дату покупки, продажи уменьшают вложения по FIFO."
    ]

    # Проверка: сумма по всем активам = общая стоимость портфеля
    total_check = sum(t['market_value_kzt'] for t in ticker_data.values())
    if abs(full_market_value_kzt - total_check) > 1:
        lines.append(f"⚠️ [Проверка] Несовпадение итоговой стоимости портфеля: {full_market_value_kzt} vs {total_check}")

    for category in sorted(tickers_by_category):
        category_total_kzt = category_market_value_kzt[category]
        category_total_usd = category_market_value_usd[category]
        category_percent = (category_total_kzt / full_market_value_kzt) * 100 if full_market_value_kzt else 0
        invested = category_invested[category]
        gain = category_gain[category]
        gain_percent = (gain / invested * 100) if invested else 0

        lines.append(f"📁 {category} - {category_percent:.1f}%")
        lines.append(f"{category_total_kzt:,.2f} ₸ | {category_total_usd:,.2f} $ | 📈 {gain_percent:+.2f}%")

        for ticker in sorted(tickers_by_category[category], key=lambda t: ticker_data[t]["market_value_kzt"], reverse=True):
            t = ticker_data[ticker]
            percent = (t["market_value_kzt"] / category_total_kzt) * 100 if category_total_kzt else 0
            gain_sign = "📈" if t["gain"] >= 0 else "📉"
            lines.append(
                f"`{ticker}` — {percent:.1f}%"
            )
            lines.append(
                f"{t['qty']} шт | {t['market_value_kzt']:,.2f} ₸ | {t['market_value_usd']:,.2f} $"
            )
            lines.append(
                f"{gain_sign} {t['gain']:,.0f} ({t['gain_percent']:+.1f}%)"
            )
            lines.append("")  # пустая строка между активами

    # Итог по портфелю
    total_gain_percent = (full_gain / full_invested * 100) if full_invested else 0
    lines.append(
        f"📈 *Итог по портфелю:* {total_gain_percent:+.2f}% | {full_gain:,.0f} ₸ | {full_gain / get_rate_today('USD'):,.0f} $"
    )
    lines.append(
        f"*Общая стоимость портфеля:* {full_market_value_kzt:,.2f} ₸ | {full_market_value_usd:,.2f} $"
    )

    return "\n".join(lines)