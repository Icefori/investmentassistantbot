import asyncio
import pandas as pd
from datetime import datetime
from bot.db import connect_db
from bot.utils.find_isin_kase import get_isin_from_kase
from bot.utils.find_isin_yahoo import get_isin_from_yahoo
from bot.scheduler.currency import fetch_rates_by_date  # функция для получения курса валюты на дату

async def get_isin_country(ticker: str, exchange: str) -> str:
    print(f"[LOG] Получаем ISIN для {ticker} ({exchange})")
    if exchange in {"KASE", "AIX"}:
        code = await get_isin_from_kase(ticker)
    else:
        code = await get_isin_from_yahoo(ticker)
    print(f"[LOG] ISIN для {ticker}: {code}")
    return code or ""

async def fetch_transactions_for_year(year: int):
    print(f"[LOG] Загружаем транзакции за {year}")
    conn = await connect_db()
    start = datetime(year, 1, 1).date()
    end = datetime(year, 12, 31).date()
    rows = await conn.fetch(
        "SELECT id, ticker, qty, price, date, exchange FROM transactions "
        "WHERE to_date(date, 'DD-MM-YYYY') >= $1 AND to_date(date, 'DD-MM-YYYY') <= $2 "
        "ORDER BY to_date(date, 'DD-MM-YYYY'), id",
        start, end
    )
    await conn.close()
    print(f"[LOG] Загружено {len(rows)} транзакций")
    return [dict(r) for r in rows]

def format_date(date_str):
    # Всегда возвращаем dd-mm-yyyy (в базе уже такой формат)
    return date_str

def fifo_match(transactions):
    print(f"[LOG] Запускаем FIFO разбор")
    buys_by_ticker = {}
    results = []
    for tx in transactions:
        ticker = tx['ticker']
        if ticker not in buys_by_ticker:
            buys_by_ticker[ticker] = []
        if tx['qty'] > 0:
            buys_by_ticker[ticker].append(tx.copy())
        elif tx['qty'] < 0:
            qty_to_sell = -tx['qty']
            buys = buys_by_ticker[ticker]
            while qty_to_sell > 0 and buys:
                buy = buys[0]
                match_qty = min(buy['qty'], qty_to_sell)
                results.append({
                    'ticker': tx['ticker'],
                    'isin': tx.get('isin', ''),
                    'exchange': tx['exchange'],
                    'date_buy': format_date(buy['date']),
                    'qty_buy': match_qty,
                    'price_buy': buy['price'],
                    'sum_buy': match_qty * buy['price'],
                    'date_sell': format_date(tx['date']),
                    'qty_sell': match_qty,
                    'price_sell': tx['price'],
                    'sum_sell': match_qty * tx['price'],
                })
                buy['qty'] -= match_qty
                qty_to_sell -= match_qty
                if buy['qty'] == 0:
                    buys.pop(0)
    print(f"[LOG] FIFO разобрано {len(results)} пар покупка-продажа")
    return results

async def calc_tax_sheet(fifo_rows):
    print(f"[LOG] Формируем налоговый лист")
    tax_rows = []
    for row in fifo_rows:
        isin = row.get('isin', '')
        exchange = row.get('exchange', '')
        if isin.startswith("KZ") or exchange == "KASE":
            continue

        qty = row['qty_sell']
        sum_buy = row['qty_buy'] * row['price_buy']
        sum_sell = row['qty_sell'] * row['price_sell']
        profit = sum_sell - sum_buy

        if profit <= 0:
            print(f"[LOG] Пропущена убыточная продажа {row['ticker']} на {row['date_sell']}")
            continue

        # Для примера считаем, что все валюты KZT (можно доработать при появлении поля currency)
        currency = "KZT"
        date_sell = row['date_sell']
        sum_sell_kzt = sum_sell
        rate = 1.0
        # Если появится поле currency, здесь добавить логику конвертации

        tax = sum_sell_kzt * 0.10

        tax_rows.append({
            'ticker': row['ticker'],
            'isin': isin,
            'exchange': exchange,
            'date_sell': format_date(date_sell),
            'qty_sell': qty,
            'sum_sell': sum_sell,
            'profit': profit,
            'currency_exchange_rate': rate,
            'sum_sell_in_KZT': sum_sell_kzt,
            'tax': tax
        })
    print(f"[LOG] В налоговом листе {len(tax_rows)} строк")
    return tax_rows

async def export_taxes_excel(year: int, filename: str = None):
    print(f"[LOG] Начинаем экспорт налогового отчета за {year}")
    transactions = await fetch_transactions_for_year(year)
    for tx in transactions:
        tx['isin'] = await get_isin_country(tx['ticker'], tx['exchange'])
    fifo_rows = fifo_match(transactions)
    df = pd.DataFrame(fifo_rows, columns=[
        'ticker', 'isin', 'exchange',
        'date_buy', 'qty_buy', 'price_buy', 'sum_buy',
        'date_sell', 'qty_sell', 'price_sell', 'sum_sell'
    ])
    tax_rows = await calc_tax_sheet(fifo_rows)
    df_tax = pd.DataFrame(tax_rows, columns=[
        'ticker', 'isin', 'exchange', 'date_sell', 'qty_sell', 'sum_sell',
        'profit', 'currency_exchange_rate', 'sum_sell_in_KZT', 'tax'
    ])
    if not filename:
        filename = f"tax_report_{year}.xlsx"
    with pd.ExcelWriter(filename) as writer:
        df.to_excel(writer, sheet_name="transactions", index=False)
        df_tax.to_excel(writer, sheet_name="taxes", index=False)
    print(f"[LOG] Экспорт завершен: {filename}")
    return filename

# Пример вызова:
# await export_taxes_excel(year=2024)