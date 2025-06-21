import io
import matplotlib.pyplot as plt
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from datetime import datetime, timedelta
from bot.db import connect_db
from bot.handlers.portfolio import calculate_portfolio
from bot.utils.parser import get_price_kase, get_price_from_yahoo
import logging
import asyncio

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

def get_weekly_dates(start_date, end_date):
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(weeks=1)
    return dates

async def get_portfolio_calculated(user_id):
    result = await calculate_portfolio(user_id)
    if not result:
        return None, None, None
    portfolio = result
    tickers_by_category = result.get("tickers_by_category", {})
    return portfolio, None, tickers_by_category

async def get_market_price_on_date(ticker: str, date: datetime) -> float | None:
    """
    Получить цену тикера на дату date.
    Для тикеров KASE пробуем get_price_kase, для остальных — get_price_from_yahoo.
    """
    # Можно добавить кэширование, чтобы не дергать API слишком часто
    # Для примера: если тикер заканчивается на .KZ, считаем KASE
    try:
        if ticker.endswith(".KZ"):
            price = await get_price_kase(ticker.replace(".KZ", ""))
            if price:
                return price
        # Для остальных — Yahoo
        price = await get_price_from_yahoo(ticker)
        return price
    except Exception as ex:
        logger.warning(f"Ошибка получения цены для {ticker} на {date}: {ex}")
        return None

async def send_portfolio_pie_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user_id = update.effective_user.id
    msg = await update.callback_query.message.reply_text("⏳ Строим пай-чарт по всему портфелю, пожалуйста, подождите...")
    await context.bot.send_chat_action(chat_id=user_id, action="upload_photo")
    portfolio, _, _ = await get_portfolio_calculated(user_id)
    if not portfolio or not portfolio.get("ticker_data") or not portfolio.get("tickers_by_category"):
        await msg.delete()
        await update.callback_query.message.reply_text("Портфель пуст. Добавьте сделки для отображения графика.")
        return

    category_values = {}
    for category, tickers in portfolio["tickers_by_category"].items():
        value = sum(portfolio["ticker_data"][ticker]["market_value_kzt"] for ticker in tickers)
        if value > 0:
            category_values[category] = value

    if not category_values:
        await msg.delete()
        await update.callback_query.message.reply_text("Нет данных для построения графика.")
        return

    labels = list(category_values.keys())
    values = list(category_values.values())

    pastel_colors = plt.cm.Pastel1.colors
    if len(labels) > len(pastel_colors):
        pastel_colors = plt.cm.Pastel2.colors + plt.cm.Pastel1.colors

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(
        values, labels=labels, autopct='%1.1f%%', startangle=140, colors=pastel_colors[:len(labels)]
    )
    ax.set_title("Распределение портфеля по категориям (₸)")

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)

    await msg.delete()
    await update.callback_query.message.reply_photo(
        photo=InputFile(buf),
        caption="Пай-чарт по категориям портфеля (₸)",
        reply_markup=get_charts_main_keyboard()
    )

async def send_category_pie_chart(update: Update, context: ContextTypes.DEFAULT_TYPE, category=None):
    await update.callback_query.answer()
    user_id = update.effective_user.id
    portfolio, _, tickers_by_category = await get_portfolio_calculated(user_id)
    if not portfolio or not tickers_by_category:
        await update.callback_query.message.reply_text("Портфель пуст. Добавьте сделки для отображения графика.")
        return

    categories = sorted(tickers_by_category.keys())
    if not category:
        await update.callback_query.message.reply_text(
            "Пожалуйста, выберите категорию для построения пай-чарта:",
            reply_markup=get_categories_keyboard(categories, "pie_category")
        )
        return

    msg = await update.callback_query.message.reply_text("⏳ Строим пай-чарт по категории, пожалуйста, подождите...")
    await context.bot.send_chat_action(chat_id=user_id, action="upload_photo")
    filtered = [portfolio["ticker_data"][ticker] for ticker in tickers_by_category.get(category, [])]
    if not filtered:
        await msg.delete()
        await update.callback_query.message.reply_text("Нет активов в выбранной категории.")
        return

    labels = [ticker for ticker in tickers_by_category[category]]
    values = [t["market_value_kzt"] for t in filtered]

    if not values or sum(values) == 0:
        await msg.delete()
        await update.callback_query.message.reply_text("Нет данных для построения графика.")
        return

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

    await msg.delete()
    await update.callback_query.message.reply_photo(
        photo=InputFile(buf),
        caption=f"Пай-чарт по категории: {category} (₸)",
        reply_markup=get_charts_main_keyboard()
    )

# --- TWR (Time-Weighted Return) график для портфеля и категории ---
async def send_portfolio_growth_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user_id = update.effective_user.id
    msg = await update.callback_query.message.reply_text("⏳ Строим график доходности портфеля, пожалуйста, подождите...")
    await context.bot.send_chat_action(chat_id=user_id, action="upload_photo")
    portfolio, _, _ = await get_portfolio_calculated(user_id)
    if not portfolio or not portfolio.get("ticker_data"):
        await msg.delete()
        await update.callback_query.message.reply_text("Нет данных по сделкам для построения графика.")
        return

    conn = await connect_db()
    txs = await conn.fetch("SELECT * FROM transactions WHERE user_id = $1 ORDER BY date", user_id)
    await conn.close()
    if not txs:
        await msg.delete()
        await update.callback_query.message.reply_text("Нет данных по сделкам для построения графика.")
        return

    ticker_currency = {}
    for ticker, t in portfolio["ticker_data"].items():
        ticker_currency[ticker] = t.get("currency", "KZT")

    all_tx_dates = sorted(datetime.strptime(tx["date"], "%d-%m-%Y").date() for tx in txs)
    if not all_tx_dates:
        await msg.delete()
        await update.callback_query.message.reply_text("Нет данных по датам.")
        return
    start_date = all_tx_dates[0]
    end_date = datetime.now().date()
    weekly_dates = get_weekly_dates(start_date, end_date)

    from bot.scheduler.currency import fetch_rates_by_date
    rates_by_date = {}
    for d in weekly_dates:
        rates, _ = await fetch_rates_by_date(datetime.combine(d, datetime.min.time()))
        rates_by_date[d] = dict(rates)

    from collections import defaultdict, deque

    # TWR расчет с учетом рыночных цен
    twr_values = []
    prev_value = None
    prev_date = None
    twr_accum = 1.0

    for i, d in enumerate(weekly_dates):
        txs_up_to_date = [tx for tx in txs if datetime.strptime(tx["date"], "%d-%m-%Y").date() <= d]
        transactions_by_ticker = defaultdict(list)
        for tx in txs_up_to_date:
            transactions_by_ticker[tx["ticker"]].append(dict(tx))
        market_value_kzt = 0.0
        # Получаем актуальные цены для всех тикеров на дату d
        price_tasks = []
        for ticker in transactions_by_ticker.keys():
            price_tasks.append(get_market_price_on_date(ticker, d))
        prices = await asyncio.gather(*price_tasks)
        ticker_prices = dict(zip(transactions_by_ticker.keys(), prices))
        for ticker, ticker_txs in transactions_by_ticker.items():
            fifo = deque()
            currency = ticker_currency.get(ticker, "KZT")
            for tx in ticker_txs:
                qty = tx["qty"]
                price = tx["price"]
                tx_currency = currency
                tx_date = tx["date"]
                if qty > 0:
                    fifo.append({"qty": qty, "price": price, "currency": tx_currency, "date": tx_date})
                elif qty < 0:
                    sell_qty = -qty
                    while sell_qty > 0 and fifo:
                        lot = fifo[0]
                        if lot["qty"] > sell_qty:
                            lot["qty"] -= sell_qty
                            sell_qty = 0
                        else:
                            sell_qty -= lot["qty"]
                            fifo.popleft()
            for lot in fifo:
                lot_currency = lot.get("currency", "KZT")
                lot_rate_now = rates_by_date[d].get(lot_currency, 1.0)
                # Используем актуальную цену!
                current_price = ticker_prices.get(ticker)
                if current_price is None:
                    current_price = lot["price"]  # fallback
                market_value_kzt += current_price * lot["qty"] * lot_rate_now

        # Определяем притоки/оттоки за период
        if i == 0:
            cash_flow = 0
            prev_value = market_value_kzt
            twr_values.append(0)
            prev_date = d
            continue

        period_txs = [tx for tx in txs if prev_date < datetime.strptime(tx["date"], "%d-%m-%Y").date() <= d]
        cash_flow = 0.0
        for tx in period_txs:
            qty = tx["qty"]
            price = tx["price"]
            ticker = tx["ticker"]
            currency = ticker_currency.get(ticker, "KZT")
            rate = rates_by_date[d].get(currency, 1.0)
            cash_flow += price * qty * rate  # Покупка: +, Продажа: -

        denominator = prev_value + cash_flow
        if denominator == 0:
            r = 0
        else:
            r = (market_value_kzt - cash_flow - prev_value) / denominator
        twr_accum *= (1 + r)
        twr_values.append((twr_accum - 1) * 100)
        prev_value = market_value_kzt
        prev_date = d

    if not twr_values or all(v == 0 for v in twr_values):
        await msg.delete()
        await update.callback_query.message.reply_text("Недостаточно данных для построения графика.")
        return

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(weekly_dates, twr_values, marker='o', color=plt.cm.Pastel1.colors[0])
    ax.set_title("Динамика доходности портфеля (TWR, %)")
    ax.set_xlabel("Дата")
    ax.set_ylabel("Доходность, %")
    ax.grid(True)
    fig.autofmt_xdate()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)

    await msg.delete()
    await update.callback_query.message.reply_photo(
        photo=InputFile(buf),
        caption="График доходности портфеля (TWR, %)",
        reply_markup=get_charts_main_keyboard()
    )

async def send_category_growth_chart(update: Update, context: ContextTypes.DEFAULT_TYPE, category=None):
    await update.callback_query.answer()
    user_id = update.effective_user.id
    portfolio, _, tickers_by_category = await get_portfolio_calculated(user_id)
    if not portfolio or not tickers_by_category:
        await update.callback_query.message.reply_text("Портфель пуст. Добавьте сделки для отображения графика.")
        return

    categories = sorted(tickers_by_category.keys())
    if not category:
        await update.callback_query.message.reply_text(
            "Пожалуйста, выберите категорию для построения графика:",
            reply_markup=get_categories_keyboard(categories, "growth_category")
        )
        return

    msg = await update.callback_query.message.reply_text("⏳ Строим график доходности по категории, пожалуйста, подождите...")
    await context.bot.send_chat_action(chat_id=user_id, action="upload_photo")

    conn = await connect_db()
    txs = await conn.fetch("SELECT * FROM transactions WHERE user_id = $1 ORDER BY date", user_id)
    await conn.close()
    if not txs:
        await msg.delete()
        await update.callback_query.message.reply_text("Нет данных по сделкам для построения графика.")
        return

    ticker_currency = {}
    for ticker in tickers_by_category.get(category, []):
        t = portfolio["ticker_data"].get(ticker)
        if t:
            ticker_currency[ticker] = t.get("currency", "KZT")

    all_tx_dates = sorted(datetime.strptime(tx["date"], "%d-%m-%Y").date() for tx in txs)
    if not all_tx_dates:
        await msg.delete()
        await update.callback_query.message.reply_text("Нет данных по датам.")
        return
    start_date = all_tx_dates[0]
    end_date = datetime.now().date()
    weekly_dates = get_weekly_dates(start_date, end_date)

    from bot.scheduler.currency import fetch_rates_by_date
    rates_by_date = {}
    for d in weekly_dates:
        rates, _ = await fetch_rates_by_date(datetime.combine(d, datetime.min.time()))
        rates_by_date[d] = dict(rates)

    from collections import defaultdict, deque

    twr_values = []
    prev_value = None
    prev_date = None
    twr_accum = 1.0

    for i, d in enumerate(weekly_dates):
        txs_up_to_date = [tx for tx in txs if datetime.strptime(tx["date"], "%d-%m-%Y").date() <= d]
        transactions_by_ticker = defaultdict(list)
        for tx in txs_up_to_date:
            transactions_by_ticker[tx["ticker"]].append(dict(tx))
        market_value_kzt = 0.0
        # Получаем актуальные цены для тикеров категории на дату d
        tickers_in_cat = [ticker for ticker in tickers_by_category.get(category, []) if ticker in transactions_by_ticker]
        price_tasks = []
        for ticker in tickers_in_cat:
            price_tasks.append(get_market_price_on_date(ticker, d))
        prices = await asyncio.gather(*price_tasks)
        ticker_prices = dict(zip(tickers_in_cat, prices))
        for ticker in tickers_in_cat:
            ticker_txs = transactions_by_ticker.get(ticker, [])
            if not ticker_txs:
                continue
            fifo = deque()
            currency = ticker_currency.get(ticker, "KZT")
            for tx in ticker_txs:
                qty = tx["qty"]
                price = tx["price"]
                tx_currency = currency
                tx_date = tx["date"]
                if qty > 0:
                    fifo.append({"qty": qty, "price": price, "currency": tx_currency, "date": tx_date})
                elif qty < 0:
                    sell_qty = -qty
                    while sell_qty > 0 and fifo:
                        lot = fifo[0]
                        if lot["qty"] > sell_qty:
                            lot["qty"] -= sell_qty
                            sell_qty = 0
                        else:
                            sell_qty -= lot["qty"]
                            fifo.popleft()
            for lot in fifo:
                lot_currency = lot.get("currency", "KZT")
                lot_rate_now = rates_by_date[d].get(lot_currency, 1.0)
                current_price = ticker_prices.get(ticker)
                if current_price is None:
                    current_price = lot["price"]
                market_value_kzt += current_price * lot["qty"] * lot_rate_now

        if i == 0:
            cash_flow = 0
            prev_value = market_value_kzt
            twr_values.append(0)
            prev_date = d
            continue

        period_txs = [tx for tx in txs if prev_date < datetime.strptime(tx["date"], "%d-%m-%Y").date() <= d and tx["ticker"] in tickers_by_category.get(category, [])]
        cash_flow = 0.0
        for tx in period_txs:
            qty = tx["qty"]
            price = tx["price"]
            ticker = tx["ticker"]
            currency = ticker_currency.get(ticker, "KZT")
            rate = rates_by_date[d].get(currency, 1.0)
            cash_flow += price * qty * rate

        denominator = prev_value + cash_flow
        if denominator == 0:
            r = 0
        else:
            r = (market_value_kzt - cash_flow - prev_value) / denominator
        twr_accum *= (1 + r)
        twr_values.append((twr_accum - 1) * 100)
        prev_value = market_value_kzt
        prev_date = d

    if not twr_values or all(v == 0 for v in twr_values):
        await msg.delete()
        await update.callback_query.message.reply_text("Недостаточно данных для построения графика.")
        return

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(weekly_dates, twr_values, marker='o', color=plt.cm.Pastel1.colors[1])
    ax.set_title(f"Динамика доходности категории {category} (TWR, %)")
    ax.set_xlabel("Дата")
    ax.set_ylabel("Доходность, %")
    ax.grid(True)
    fig.autofmt_xdate()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close(fig)

    await msg.delete()
    await update.callback_query.message.reply_photo(
        photo=InputFile(buf),
        caption=f"График доходности категории {category} (TWR, %)",
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
        user_id = update.effective_user.id
        portfolio, _, tickers_by_category = await get_portfolio_calculated(user_id)
        categories = sorted(tickers_by_category.keys()) if tickers_by_category else []
        await update.callback_query.message.reply_text(
            "Пожалуйста, выберите категорию для построения пай-чарта:",
            reply_markup=get_categories_keyboard(categories, "pie_category")
        )
    elif data.startswith("chart_pie_category|"):
        category = data.split("|", 1)[1]
        await send_category_pie_chart(update, context, category=category)
    elif data == "chart_growth_category":
        user_id = update.effective_user.id
        portfolio, _, tickers_by_category = await get_portfolio_calculated(user_id)
        categories = sorted(tickers_by_category.keys()) if tickers_by_category else []
        await update.callback_query.message.reply_text(
            "Пожалуйста, выберите категорию для построения графика:",
            reply_markup=get_categories_keyboard(categories, "growth_category")
        )
    elif data.startswith("chart_growth_category|"):
        category = data.split("|", 1)[1]
        await send_category_growth_chart(update, context, category=category)
    elif data == "chart_back_to_charts_menu":
        await update.callback_query.message.reply_text(
            "Выберите, какой график или пай-чарт вы хотите посмотреть:",
            reply_markup=get_charts_main_keyboard()
        )

portfolio_charts_handler = CallbackQueryHandler(
    portfolio_chart_callback,
    pattern=r"^chart_"
)