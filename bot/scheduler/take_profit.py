import asyncio
from datetime import datetime, timedelta
from bot.db import connect_db
from bot.utils.parser import get_price_kase, get_price_from_yahoo
from bot.scheduler.currency import fetch_exchange_rates

ALERT_THRESHOLD = 0.1499  # >=14.99%

async def check_take_profit_alerts(send_alert_func):
    conn = await connect_db()
    transactions = await conn.fetch("SELECT * FROM transactions ORDER BY ticker, date")
    await conn.close()

    # Группируем по тикеру
    transactions_by_ticker = {}
    for tx in transactions:
        ticker = tx["ticker"]
        transactions_by_ticker.setdefault(ticker, []).append(dict(tx))

    exchange_rates = await fetch_exchange_rates()
    get_rate = lambda cur: (exchange_rates.get(cur) or 1.0)

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
            percent_gain = (current_price - entry_price) / entry_price

            if percent_gain >= ALERT_THRESHOLD:
                # Формируем сообщение
                percent_str = f"{percent_gain*100:+.0f}%"
                entry_price_str = f"{entry_price:,.0f} {currency}"
                current_price_str = f"{current_price:,.0f} {currency}"
                qty_str = f"{pos['qty']}"
                date_str = pos["date"]

                msg = (
                    f"✅ Take Profit\n"
                    f"🎯 Актив `{ticker}` вырос на {percent_str} от цены входа\n"
                    f"(вход: {entry_price_str} → текущая: {current_price_str})\n"
                    f"Можно продать {qty_str} акций (покупка от {date_str})\n"
                    f"💡 Предлагаю рассмотреть фиксацию части прибыли или стоп-перенос"
                )
                await send_alert_func(msg)

# Пример send_alert_func:
# async def send_alert_func(msg):
#     await bot.send_message(chat_id=..., text=msg, parse_mode="Markdown")