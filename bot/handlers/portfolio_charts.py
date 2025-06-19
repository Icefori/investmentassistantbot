import io
import matplotlib.pyplot as plt
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from collections import defaultdict
from datetime import datetime, date, timedelta
from bot.db import connect_db
from bot.scheduler.currency import fetch_rates_by_date

# --- Вспомогательные функции ---

async def get_portfolio_data(user_id):
    conn = await connect_db()
    portfolio_rows = await conn.fetch("SELECT * FROM portfolio WHERE user_id = $1", user_id)
    await conn.close()
    return portfolio_rows

async def get_transactions(user_id):
    conn = await connect_db()
    txs = await conn.fetch("SELECT * FROM transactions WHERE user_id = $1 ORDER BY date", user_id)
    await conn.close()
    return txs

# --- Пай-чарт по всему портфелю ---

async def send_portfolio_pie_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    portfolio_rows = await get_portfolio_data(user_id)
    if not portfolio_rows:
        await update.callback_query.answer("Портфель пуст.")
        return

    # Суммируем стоимость по тикерам
    values = []
    labels = []
    for row in portfolio_rows:
        labels.append(row["ticker"])
        values.append(row["market_value_kzt"])

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=140)
    ax.set_title("Распределение активов по портфелю")

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)

    await update.callback_query.message.reply_photo(photo=InputFile(buf), caption="Пай-чарт по всему портфелю")

# --- Пай-чарт по категории ---

async def send_category_pie_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    portfolio_rows = await get_portfolio_data(user_id)
    if not portfolio_rows:
        await update.callback_query.answer("Портфель пуст.")
        return

    # Получаем список категорий
    categories = sorted(set(row["category"] for row in portfolio_rows))
    # Если категория не выбрана, показываем кнопки выбора
    if len(context.args) == 0:
        keyboard = [
            [InlineKeyboardButton(cat, callback_data=f"pie_category|{cat}")]
            for cat in categories
        ]
        await update.callback_query.message.reply_text(
            "Выберите категорию для пай-чарта:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # Категория выбрана
    category = context.args[0]
    filtered = [row for row in portfolio_rows if row["category"] == category]
    if not filtered:
        await update.callback_query.answer("Нет активов в выбранной категории.")
        return

    labels = [row["ticker"] for row in filtered]
    values = [row["market_value_kzt"] for row in filtered]

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=140)
    ax.set_title(f"Распределение по категории: {category}")

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)

    await update.callback_query.message.reply_photo(photo=InputFile(buf), caption=f"Пай-чарт по категории: {category}")

# --- График роста портфеля (общий) ---

async def send_portfolio_growth_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    txs = await get_transactions(user_id)
    if not txs:
        await update.callback_query.answer("Нет данных по сделкам.")
        return

    # Собираем даты
    all_dates = sorted({datetime.strptime(tx["date"], "%d-%m-%Y").date() for tx in txs})
    if not all_dates:
        await update.callback_query.answer("Нет данных по датам.")
        return

    # Получаем курсы валют на все даты
    rates_by_date = {}
    for d in all_dates:
        rates, _ = await fetch_rates_by_date(datetime.combine(d, datetime.min.time()))
        rates_by_date[d] = dict(rates)
        rates_by_date[d]["KZT"] = 1.0
        rates_by_date[d]["USD"] = rates_by_date[d].get("USD", 1.0)

    # Для каждой даты считаем стоимость портфеля (нереализованная прибыль)
    portfolio_values = []
    prev_value = None
    for d in all_dates:
        # Получаем все сделки до этой даты включительно
        txs_up_to_date = [tx for tx in txs if datetime.strptime(tx["date"], "%d-%m-%Y").date() <= d]
        # FIFO по тикерам
        from collections import defaultdict, deque
        transactions_by_ticker = defaultdict(list)
        for tx in txs_up_to_date:
            transactions_by_ticker[tx["ticker"]].append(dict(tx))
        invested = 0.0
        market_value = 0.0
        for ticker, ticker_txs in transactions_by_ticker.items():
            fifo = deque()
            total_qty = 0
            currency = ticker_txs[0]["currency"]
            for tx in ticker_txs:
                qty = tx["qty"]
                price = tx["price"]
                tx_date = datetime.strptime(tx["date"], "%d-%m-%Y").date()
                rate_on_date = rates_by_date[tx_date].get(currency, 1.0)
                if qty > 0:
                    fifo.append({"qty": qty, "price": price, "rate": rate_on_date, "currency": currency})
                    total_qty += qty
                elif qty < 0:
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
            for lot in fifo:
                if lot["currency"] == "KZT":
                    invested += lot["price"] * lot["qty"]
                elif lot["currency"] == "USD":
                    invested += lot["price"] * lot["qty"] * lot["rate"]
                else:
                    invested += lot["price"] * lot["qty"] * lot["rate"]
            # Для простоты: считаем рыночную стоимость = вложения (без реальной переоценки)
            # Можно доработать, если есть API для исторических цен
            market_value += invested  # или используйте актуальную цену, если есть

        # Прирост в %
        if invested > 0:
            gain_percent = ((market_value - invested) / invested) * 100
        else:
            gain_percent = 0
        portfolio_values.append(gain_percent)
        prev_value = market_value

    # График
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(all_dates, portfolio_values, marker='o')
    ax.set_title("Динамика прироста портфеля (%)")
    ax.set_xlabel("Дата")
    ax.set_ylabel("% прироста")
    ax.grid(True)
    fig.autofmt_xdate()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)

    await update.callback_query.message.reply_photo(photo=InputFile(buf), caption="График прироста портфеля (%)")

# --- Inline-кнопки для портфеля ---

def get_portfolio_inline_keyboard(categories):
    keyboard = [
        [InlineKeyboardButton("📊 Пай-чарт (весь портфель)", callback_data="pie_all")],
        [InlineKeyboardButton("📈 График (весь портфель)", callback_data="growth_all")],
        [InlineKeyboardButton("📊 Пай-чарт по категории", callback_data="pie_category")],
        [InlineKeyboardButton("📈 График по категории", callback_data="growth_category")],
    ]
    return InlineKeyboardMarkup(keyboard)

# --- Callback обработчик ---

async def portfolio_chart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    context.args = []
    if data == "pie_all":
        await send_portfolio_pie_chart(update, context)
    elif data == "growth_all":
        await send_portfolio_growth_chart(update, context)
    elif data == "pie_category":
        await send_category_pie_chart(update, context)
    elif data.startswith("pie_category|"):
        category = data.split("|", 1)[1]
        context.args = [category]
        await send_category_pie_chart(update, context)
    # growth_category можно реализовать аналогично пай-чарту по категории

# --- Для app.py ---

portfolio_charts_handler = CallbackQueryHandler(portfolio_chart_callback, pattern="^(pie_all|growth_all|pie_category|pie_category\|.+)$")