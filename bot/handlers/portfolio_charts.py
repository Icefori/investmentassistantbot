import io
import matplotlib.pyplot as plt
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from datetime import datetime
from bot.db import connect_db
from bot.handlers.portfolio import calculate_portfolio
import logging

logger = logging.getLogger(__name__)

def get_charts_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Пай-чарт (весь портфель)", callback_data="chart_pie_all")],
        [InlineKeyboardButton("📊 Пай-чарт по категории", callback_data="chart_pie_category")],
        [InlineKeyboardButton("📈 График (весь портфель)", callback_data="chart_growth_all")],
        [InlineKeyboardButton("📈 График по категории", callback_data="chart_growth_category")],
    ])

def get_categories_keyboard(categories, prefix):
    keyboard = [
        [InlineKeyboardButton(cat, callback_data=f"chart_{prefix}|{cat}")]
        for cat in categories
    ]
    keyboard.append([InlineKeyboardButton("🔙 Назад к выбору графика", callback_data="chart_back_to_charts_menu")])
    return InlineKeyboardMarkup(keyboard)

async def get_portfolio_calculated(user_id):
    result = await calculate_portfolio(user_id)
    if not result:
        return None, None, None
    portfolio = result
    tickers_by_category = result.get("tickers_by_category", {})
    return portfolio, None, tickers_by_category

async def send_portfolio_pie_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user_id = update.effective_user.id
    await context.bot.send_chat_action(chat_id=user_id, action="upload_photo")
    portfolio, _, _ = await get_portfolio_calculated(user_id)
    if not portfolio or not portfolio.get("ticker_data") or not portfolio.get("tickers_by_category"):
        await update.callback_query.answer("Портфель пуст. Добавьте сделки для отображения графика.", show_alert=True)
        return

    # Группируем по категориям
    category_values = {}
    for category, tickers in portfolio["tickers_by_category"].items():
        value = sum(portfolio["ticker_data"][ticker]["market_value_kzt"] for ticker in tickers)
        if value > 0:
            category_values[category] = value

    if not category_values:
        await update.callback_query.answer("Нет данных для построения графика.", show_alert=True)
        return

    labels = list(category_values.keys())
    values = list(category_values.values())

    # Используем пастельную палитру matplotlib
    pastel_colors = plt.cm.Pastel1.colors  # 9 пастельных цветов
    # Если категорий больше 9, используем Pastel2 или комбинируем
    if len(labels) > len(pastel_colors):
        pastel_colors = plt.cm.Pastel2.colors + plt.cm.Pastel1.colors

    fig, ax = plt.subplots(figsize=(6, 6))
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, autopct='%1.1f%%', startangle=140, colors=pastel_colors[:len(labels)]
    )
    ax.set_title("Распределение портфеля по категориям (₸)")

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)

    await update.callback_query.message.reply_photo(
        photo=InputFile(buf),
        caption="Пай-чарт по категориям портфеля (₸)",
        reply_markup=get_charts_main_keyboard()
    )

async def send_category_pie_chart(update: Update, context: ContextTypes.DEFAULT_TYPE, category=None):
    await update.callback_query.answer()
    user_id = update.effective_user.id
    await context.bot.send_chat_action(chat_id=user_id, action="upload_photo")
    portfolio, _, tickers_by_category = await get_portfolio_calculated(user_id)
    if not portfolio or not tickers_by_category:
        await update.callback_query.answer("Портфель пуст. Добавьте сделки для отображения графика.", show_alert=True)
        return

    categories = sorted(tickers_by_category.keys())
    if not category:
        await update.callback_query.message.reply_text(
            "Пожалуйста, выберите категорию для построения пай-чарта:",
            reply_markup=get_categories_keyboard(categories, "pie_category")
        )
        return

    filtered = [portfolio["ticker_data"][ticker] for ticker in tickers_by_category.get(category, [])]
    if not filtered:
        await update.callback_query.answer("Нет активов в выбранной категории.", show_alert=True)
        return

    labels = [ticker for ticker in tickers_by_category[category]]
    values = [t["market_value_kzt"] for t in filtered]

    if not values or sum(values) == 0:
        await update.callback_query.answer("Нет данных для построения графика.", show_alert=True)
        return

    # Используем пастельную палитру
    pastel_colors = plt.cm.Pastel1.colors
    if len(labels) > len(pastel_colors):
        pastel_colors = plt.cm.Pastel2.colors + plt.cm.Pastel1.colors

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=140, colors=pastel_colors[:len(labels)])
    ax.set_title(f"Распределение по категории: {category} (₸)")

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)

    await update.callback_query.message.reply_photo(
        photo=InputFile(buf),
        caption=f"Пай-чарт по категории: {category} (₸)",
        reply_markup=get_charts_main_keyboard()
    )

async def send_portfolio_growth_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user_id = update.effective_user.id
    await context.bot.send_chat_action(chat_id=user_id, action="upload_photo")
    portfolio, _, _ = await get_portfolio_calculated(user_id)
    if not portfolio or not portfolio.get("ticker_data"):
        await update.callback_query.answer("Нет данных по сделкам для построения графика.", show_alert=True)
        return

    conn = await connect_db()
    txs = await conn.fetch("SELECT * FROM transactions WHERE user_id = $1 ORDER BY date", user_id)
    await conn.close()
    if not txs:
        await update.callback_query.answer("Нет данных по сделкам для построения графика.", show_alert=True)
        return

    # Получаем валюту тикера из портфеля
    ticker_currency = {}
    for ticker, t in portfolio["ticker_data"].items():
        ticker_currency[ticker] = t.get("currency", "KZT")

    all_dates = sorted({datetime.strptime(tx["date"], "%d-%m-%Y").date() for tx in txs})
    if not all_dates:
        await update.callback_query.answer("Нет данных по датам.", show_alert=True)
        return

    from bot.scheduler.currency import fetch_rates_by_date
    # Для каждой даты получаем курс USD/KZT
    rates_by_date = {}
    for d in all_dates:
        rates, _ = await fetch_rates_by_date(datetime.combine(d, datetime.min.time()))
        rates_by_date[d] = dict(rates)

    portfolio_values = []
    invested_values = []
    percent_changes = []

    from collections import defaultdict, deque

    for d in all_dates:
        txs_up_to_date = [tx for tx in txs if datetime.strptime(tx["date"], "%d-%m-%Y").date() <= d]
        transactions_by_ticker = defaultdict(list)
        for tx in txs_up_to_date:
            transactions_by_ticker[tx["ticker"]].append(dict(tx))
        market_value_kzt = 0.0
        invested_kzt = 0.0
        for ticker, ticker_txs in transactions_by_ticker.items():
            fifo = deque()
            total_qty = 0
            currency = ticker_currency.get(ticker, "KZT")
            for tx in ticker_txs:
                qty = tx["qty"]
                price = tx["price"]
                tx_currency = currency
                if qty > 0:
                    fifo.append({"qty": qty, "price": price, "currency": tx_currency})
                    total_qty += qty
                    # Вложения считаем по курсу на дату сделки
                    rate = rates_by_date[d].get(tx_currency, 1.0)
                    invested_kzt += price * qty * rate
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
            # Рыночная стоимость по курсу на дату d
            rate = rates_by_date[d].get(currency, 1.0)
            for lot in fifo:
                lot_currency = lot.get("currency", "KZT")
                lot_rate = rates_by_date[d].get(lot_currency, 1.0)
                market_value_kzt += lot["price"] * lot["qty"] * lot_rate
        portfolio_values.append(market_value_kzt)
        invested_values.append(invested_kzt if invested_kzt > 0 else 1)  # чтобы не делить на 0
        percent_changes.append(
            ((market_value_kzt - invested_kzt) / invested_kzt * 100) if invested_kzt > 0 else 0
        )

    if not percent_changes or all(v == 0 for v in percent_changes):
        await update.callback_query.answer("Недостаточно данных для построения графика.", show_alert=True)
        return

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(all_dates, percent_changes, marker='o')
    ax.set_title("Динамика доходности портфеля (%)")
    ax.set_xlabel("Дата")
    ax.set_ylabel("Доходность, %")
    ax.grid(True)
    fig.autofmt_xdate()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)

    await update.callback_query.message.reply_photo(
        photo=InputFile(buf),
        caption="График доходности портфеля (%)",
        reply_markup=get_charts_main_keyboard()
    )

async def send_category_growth_chart(update: Update, context: ContextTypes.DEFAULT_TYPE, category=None):
    await update.callback_query.answer()
    user_id = update.effective_user.id
    await context.bot.send_chat_action(chat_id=user_id, action="upload_photo")
    portfolio, _, tickers_by_category = await get_portfolio_calculated(user_id)
    if not portfolio or not tickers_by_category:
        await update.callback_query.answer("Портфель пуст. Добавьте сделки для отображения графика.", show_alert=True)
        return

    categories = sorted(tickers_by_category.keys())
    if not category:
        await update.callback_query.message.reply_text(
            "Пожалуйста, выберите категорию для построения графика:",
            reply_markup=get_categories_keyboard(categories, "growth_category")
        )
        return

    conn = await connect_db()
    txs = await conn.fetch("SELECT * FROM transactions WHERE user_id = $1 ORDER BY date", user_id)
    await conn.close()
    if not txs:
        await update.callback_query.answer("Нет данных по сделкам для построения графика.", show_alert=True)
        return

    ticker_currency = {}
    for ticker in tickers_by_category.get(category, []):
        t = portfolio["ticker_data"].get(ticker)
        if t:
            ticker_currency[ticker] = t.get("currency", "KZT")

    all_dates = sorted({datetime.strptime(tx["date"], "%d-%m-%Y").date() for tx in txs})
    if not all_dates:
        await update.callback_query.answer("Нет данных по датам.", show_alert=True)
        return

    from bot.scheduler.currency import fetch_rates_by_date
    rates_by_date = {}
    for d in all_dates:
        rates, _ = await fetch_rates_by_date(datetime.combine(d, datetime.min.time()))
        rates_by_date[d] = dict(rates)

    percent_changes = []

    from collections import defaultdict, deque

    for d in all_dates:
        txs_up_to_date = [tx for tx in txs if datetime.strptime(tx["date"], "%d-%m-%Y").date() <= d]
        transactions_by_ticker = defaultdict(list)
        for tx in txs_up_to_date:
            transactions_by_ticker[tx["ticker"]].append(dict(tx))
        market_value_kzt = 0.0
        invested_kzt = 0.0
        for ticker in tickers_by_category.get(category, []):
            ticker_txs = transactions_by_ticker.get(ticker, [])
            if not ticker_txs:
                continue
            fifo = deque()
            total_qty = 0
            currency = ticker_currency.get(ticker, "KZT")
            for tx in ticker_txs:
                qty = tx["qty"]
                price = tx["price"]
                tx_currency = currency
                if qty > 0:
                    fifo.append({"qty": qty, "price": price, "currency": tx_currency})
                    total_qty += qty
                    rate = rates_by_date[d].get(tx_currency, 1.0)
                    invested_kzt += price * qty * rate
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
            rate = rates_by_date[d].get(currency, 1.0)
            for lot in fifo:
                lot_currency = lot.get("currency", "KZT")
                lot_rate = rates_by_date[d].get(lot_currency, 1.0)
                market_value_kzt += lot["price"] * lot["qty"] * lot_rate
        invested_kzt = invested_kzt if invested_kzt > 0 else 1
        percent_changes.append(
            ((market_value_kzt - invested_kzt) / invested_kzt * 100) if invested_kzt > 0 else 0
        )

    if not percent_changes or all(v == 0 for v in percent_changes):
        await update.callback_query.answer("Недостаточно данных для построения графика.", show_alert=True)
        return

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(all_dates, percent_changes, marker='o')
    ax.set_title(f"Динамика доходности категории {category} (%)")
    ax.set_xlabel("Дата")
    ax.set_ylabel("Доходность, %")
    ax.grid(True)
    fig.autofmt_xdate()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)

    await update.callback_query.message.reply_photo(
        photo=InputFile(buf),
        caption=f"График доходности категории {category} (%)",
        reply_markup=get_charts_main_keyboard()
    )

async def portfolio_chart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    logger.info(f"Пай-чарт callback: user_id={update.effective_user.id}, data={data}")
    if data == "chart_pie_all":
        await send_portfolio_pie_chart(update, context)
    elif data == "chart_growth_all":
        await send_portfolio_growth_chart(update, context)
    elif data == "chart_pie_category":
        await send_category_pie_chart(update, context)
    elif data.startswith("chart_pie_category|"):
        category = data.split("|", 1)[1]
        await send_category_pie_chart(update, context, category=category)
    elif data == "chart_growth_category":
        await send_category_growth_chart(update, context)
    elif data.startswith("chart_growth_category|"):
        category = data.split("|", 1)[1]
        await send_category_growth_chart(update, context, category=category)
    elif data == "chart_back_to_charts_menu":
        user_id = update.effective_user.id
        portfolio, _, tickers_by_category = await get_portfolio_calculated(user_id)
        categories = sorted(tickers_by_category.keys()) if tickers_by_category else []
        await update.callback_query.message.reply_text(
            "Выберите, какой график или пай-чарт вы хотите посмотреть:",
            reply_markup=get_charts_main_keyboard()
        )

portfolio_charts_handler = CallbackQueryHandler(
    portfolio_chart_callback,
    pattern=r"^chart_"
)