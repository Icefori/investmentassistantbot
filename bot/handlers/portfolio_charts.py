import io
import matplotlib.pyplot as plt
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from datetime import datetime
from bot.handlers.portfolio import summarize_portfolio
from bot.db import connect_db
from bot.handlers.portfolio import calculate_portfolio  # Импортируем один раз в начале

# --- Inline-кнопки для портфеля ---
def get_portfolio_inline_keyboard(categories):
    keyboard = [
        [InlineKeyboardButton("📊 Пай-чарт (весь портфель)", callback_data="pie_all")],
        [InlineKeyboardButton("📈 График (весь портфель)", callback_data="growth_all")],
        [InlineKeyboardButton("📊 Пай-чарт по категории", callback_data="pie_category")],
    ]
    if categories:
        for cat in categories:
            keyboard.append([InlineKeyboardButton(f"Пай-чарт: {cat}", callback_data=f"pie_category|{cat}")])
    keyboard.append([InlineKeyboardButton("🔙 Назад к портфелю", callback_data="back_to_portfolio")])
    return InlineKeyboardMarkup(keyboard)

# --- Получение расчетных данных портфеля ---
async def get_portfolio_calculated(user_id):
    portfolio, portfolio_rows, tickers_by_category = await calculate_portfolio(user_id)
    return portfolio, portfolio_rows, tickers_by_category

# --- Пай-чарт по всему портфелю ---
async def send_portfolio_pie_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    portfolio, portfolio_rows, _ = await get_portfolio_calculated(user_id)
    if not portfolio_rows:
        await update.callback_query.answer("Портфель пуст. Добавьте сделки для отображения графика.", show_alert=True)
        return

    values = []
    labels = []
    for ticker, t in portfolio["ticker_data"].items():
        labels.append(ticker)
        values.append(t["market_value_kzt"])

    if not values or sum(values) == 0:
        await update.callback_query.answer("Нет данных для построения графика.", show_alert=True)
        return

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=140)
    ax.set_title("Распределение активов по портфелю (₸)")

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)

    await update.callback_query.message.reply_photo(
        photo=InputFile(buf),
        caption="Пай-чарт по всему портфелю (₸)",
        reply_markup=get_portfolio_inline_keyboard(sorted(portfolio["tickers_by_category"].keys()))
    )

# --- Пай-чарт по категории ---
async def send_category_pie_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    portfolio, portfolio_rows, tickers_by_category = await get_portfolio_calculated(user_id)
    if not portfolio_rows:
        await update.callback_query.answer("Портфель пуст. Добавьте сделки для отображения графика.", show_alert=True)
        return

    categories = sorted(tickers_by_category.keys())
    if not context.args:
        keyboard = [
            [InlineKeyboardButton(cat, callback_data=f"pie_category|{cat}")]
            for cat in categories
        ]
        keyboard.append([InlineKeyboardButton("🔙 Назад к портфелю", callback_data="back_to_portfolio")])
        await update.callback_query.message.reply_text(
            "Пожалуйста, выберите категорию для построения пай-чарта:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    category = context.args[0]
    filtered = [portfolio["ticker_data"][ticker] for ticker in tickers_by_category[category]]
    if not filtered:
        await update.callback_query.answer("Нет активов в выбранной категории.", show_alert=True)
        return

    labels = [ticker for ticker in tickers_by_category[category]]
    values = [t["market_value_kzt"] for t in filtered]

    if not values or sum(values) == 0:
        await update.callback_query.answer("Нет данных для построения графика.", show_alert=True)
        return

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=140)
    ax.set_title(f"Распределение по категории: {category} (₸)")

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)

    await update.callback_query.message.reply_photo(
        photo=InputFile(buf),
        caption=f"Пай-чарт по категории: {category} (₸)",
        reply_markup=get_portfolio_inline_keyboard(categories)
    )

# --- График роста портфеля (общий) ---
async def send_portfolio_growth_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    portfolio, portfolio_rows, _ = await calculate_portfolio(user_id)
    if not portfolio_rows:
        await update.callback_query.answer("Нет данных по сделкам для построения графика.", show_alert=True)
        return

    conn = await connect_db()
    txs = await conn.fetch("SELECT * FROM transactions WHERE user_id = $1 ORDER BY date", user_id)
    await conn.close()
    if not txs:
        await update.callback_query.answer("Нет данных по сделкам для построения графика.", show_alert=True)
        return

    all_dates = sorted({datetime.strptime(tx["date"], "%d-%m-%Y").date() for tx in txs})
    if not all_dates:
        await update.callback_query.answer("Нет данных по датам.", show_alert=True)
        return

    from bot.scheduler.currency import fetch_rates_by_date
    today_rates, _ = await fetch_rates_by_date(datetime.now())
    usd_rate = dict(today_rates).get("USD", 1.0)

    portfolio_values = []
    for d in all_dates:
        from collections import defaultdict, deque
        txs_up_to_date = [tx for tx in txs if datetime.strptime(tx["date"], "%d-%m-%Y").date() <= d]
        transactions_by_ticker = defaultdict(list)
        for tx in txs_up_to_date:
            transactions_by_ticker[tx["ticker"]].append(dict(tx))
        market_value_kzt = 0.0
        for ticker, ticker_txs in transactions_by_ticker.items():
            fifo = deque()
            total_qty = 0
            currency = ticker_txs[0]["currency"]
            for tx in ticker_txs:
                qty = tx["qty"]
                price = tx["price"]
                if qty > 0:
                    fifo.append({"qty": qty, "price": price, "currency": currency})
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
            for lot in fifo:
                if lot["currency"] == "KZT":
                    market_value_kzt += lot["price"] * lot["qty"]
                elif lot["currency"] == "USD":
                    market_value_kzt += lot["price"] * lot["qty"] * usd_rate
                else:
                    market_value_kzt += lot["price"] * lot["qty"] * usd_rate  # fallback
        portfolio_values.append(market_value_kzt)

    if not portfolio_values or sum(portfolio_values) == 0:
        await update.callback_query.answer("Недостаточно данных для построения графика.", show_alert=True)
        return

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(all_dates, portfolio_values, marker='o')
    ax.set_title("Динамика стоимости портфеля (₸)")
    ax.set_xlabel("Дата")
    ax.set_ylabel("Стоимость, ₸")
    ax.grid(True)
    fig.autofmt_xdate()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)

    await update.callback_query.message.reply_photo(
        photo=InputFile(buf),
        caption="График динамики стоимости портфеля (₸)",
        reply_markup=get_portfolio_inline_keyboard(sorted(portfolio["tickers_by_category"].keys()))
    )

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
    elif data == "back_to_portfolio":
        await summarize_portfolio(update, context)

# --- Для app.py ---
portfolio_charts_handler = CallbackQueryHandler(
    portfolio_chart_callback,
    pattern="^(pie_all|growth_all|pie_category|pie_category\|.+|back_to_portfolio)$"
)