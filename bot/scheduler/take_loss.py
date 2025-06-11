import asyncio
from datetime import datetime
from bot.db import connect_db
from bot.utils.parser import get_price_kase, get_price_from_yahoo
from bot.scheduler.currency import fetch_exchange_rates_full  # исправлено

ALERT_THRESHOLD = -0.10  # <= -10%

async def check_take_loss_alerts(send_alert_func):
    conn = await connect_db()
    transactions = await conn.fetch("SELECT * FROM transactions ORDER BY ticker, date")
    await conn.close()

    # Группируем по тикеру
    transactions_by_ticker = {}
    for tx in transactions:
        ticker = tx["ticker"]
        transactions_by_ticker.setdefault(ticker, []).append(dict(tx))

    today_rates, *_ = await fetch_exchange_rates_full()
    get_rate = lambda cur: (today_rates.get(cur) or 1.0)

    for ticker, txs in transactions_by_ticker.items():
        # Сортируем по дате
        txs = sorted(txs, key=lambda x: datetime.strptime(x["date"], "%d-%m-%Y"))

        # FIFO очередь: [(остаток, цена входа, дата, валюта)]
        positions = []
        for tx in txs:
            qty = tx["qty"]
            price = tx["price"]
            date_ = tx["date"]
            currency = tx.get("currency", "KZT")
            if qty > 0:
                positions.append({"qty": qty, "price": price, "date": date_, "currency": currency})
            else:
                sell_qty = -qty
                # Снимаем продажи с FIFO позиций
                while sell_qty > 0 and positions:
                    pos = positions[0]
                    if pos["qty"] > sell_qty:
                        pos["qty"] -= sell_qty
                        sell_qty = 0
                    else:
                        sell_qty -= pos["qty"]
                        positions.pop(0)

        # Для каждой открытой позиции (остатка) делаем проверку
        for pos in positions:
            if pos["qty"] <= 0:
                continue
            # Получаем цену за вчера (или последнюю)
            currency = pos["currency"]
            if currency == "KZT":
                current_price = await get_price_kase(ticker)
            else:
                current_price = await get_price_from_yahoo(ticker)
                if current_price is None:
                    current_price = await get_price_kase(ticker)
            if current_price is None:
                continue

            entry_price = pos["price"]
            percent_loss = (current_price - entry_price) / entry_price

            if percent_loss <= ALERT_THRESHOLD:
                # Формируем сообщение
                percent_str = f"{percent_loss*100:+.1f}%"
                entry_price_str = f"{entry_price:,.0f} {currency}"
                current_price_str = f"{current_price:,.0f} {currency}"
                qty_str = f"{pos['qty']}"
                date_str = pos["date"]

                msg = (
                    f"❌ Stop Loss\n"
                    f"📉 Потери превышают допустимое значение!\n"
                    f"Актив `{ticker}` упал на {percent_str} от цены входа "
                    f"(вход: {entry_price_str} → текущая: {current_price_str})\n"
                    f"⚠️ Можно продать {qty_str} акций (покупка от {date_str})\n"
                    f"💡 Рекомендуется пересмотреть позицию, возможна дальнейшая просадка"
                )
                await send_alert_func(msg)