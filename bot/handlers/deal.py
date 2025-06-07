from datetime import datetime 
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from bot.db import connect_db

CURRENCY_CODES = {"KZT", "USD", "EUR", "RUB", "GBP", "CHF", "JPY", "CNY"}


async def handle_deal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message.text.strip()
        parts = message.split()

        if len(parts) < 3:
            await update.message.reply_text(
                "❗ Недостаточно данных. Введите: тикер, количество и цену.",
                parse_mode="Markdown"
            )
            return

        ticker = parts[0].upper()
        qty = int(parts[1])
        price = float(parts[2].replace(",", ".").strip())
        currency = None
        date = datetime.today().strftime("%d-%m-%Y")

        for p in parts[3:]:
            if len(p) == 3 and p.upper() in CURRENCY_CODES:
                currency = p.upper()
            elif len(p) == 10 and "-" in p:
                try:
                    date = datetime.strptime(p, "%d-%m-%Y").strftime("%d-%m-%Y")
                except ValueError:
                    await update.message.reply_text(
                        "❌ Ошибка: неверный формат даты. Используйте `дд-мм-гггг`",
                        parse_mode="Markdown"
                    )
                    return

        conn = await connect_db()
        row = await conn.fetchrow("SELECT * FROM portfolio WHERE ticker = $1", ticker)
        await conn.close()

        if row is None:
            context.user_data["pending_deal"] = {
                "ticker": ticker,
                "qty": qty,
                "price": price,
                "date": date,
                "currency": currency
            }

            await update.message.reply_text(f"🆕 Новый актив: {ticker}")

            if not currency:
                buttons = [
                    [InlineKeyboardButton("KZT", callback_data="currency_KZT"),
                     InlineKeyboardButton("USD", callback_data="currency_USD")]
                ]
                await update.message.reply_text("💱 Выберите валюту:", reply_markup=InlineKeyboardMarkup(buttons))
            else:
                await ask_category(update)
            return

        await save_transaction(ticker, qty, price, date)
        sign = "➕ Покупка" if qty > 0 else "➖ Продажа"
        response = (
            f"✅ Сделка добавлена\n\n"
            f"*{ticker}* | {sign}\n"
            f"{abs(qty)} шт × {price:.2f} {currency or 'KZT'}\n"
            f"📅 Дата: {date}"
        )
        await update.message.reply_text(response, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


async def ask_category(update_or_query):
    buttons = [
        [InlineKeyboardButton("KZ", callback_data="category_KZ"),
         InlineKeyboardButton("ETF", callback_data="category_ETF"),
         InlineKeyboardButton("BONDS", callback_data="category_BONDS"),
         InlineKeyboardButton("GOLD", callback_data="category_GOLD")]
    ]
    if hasattr(update_or_query, "message"):
        await update_or_query.message.reply_text("📂 Выберите категорию:", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update_or_query.message.reply_text("📂 Выберите категорию:", reply_markup=InlineKeyboardMarkup(buttons))


async def save_transaction(ticker, qty, price, date):
    conn = await connect_db()
    await conn.execute(
        "INSERT INTO transactions (ticker, qty, price, date) VALUES ($1, $2, $3, $4)",
        ticker, qty, price, date
    )
    await conn.close()


async def choose_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("currency_"):
        currency = data.split("_")[1]
        pending = context.user_data.get("pending_deal")
        if not pending:
            await query.edit_message_text("⚠️ Нет ожидающей сделки.")
            return
        pending["currency"] = currency
        await query.edit_message_text(f"💱 Валюта выбрана: {currency}")
        await ask_category(query)

    elif data.startswith("category_"):
        category = data.split("_")[1]
        pending = context.user_data.pop("pending_deal", None)
        if not pending:
            await query.edit_message_text("⚠️ Нет ожидающей сделки.")
            return

        ticker = pending["ticker"]
        qty = pending["qty"]
        price = pending["price"]
        date = pending["date"]
        currency = pending["currency"]

        conn = await connect_db()
        await conn.execute(
            "INSERT INTO portfolio (ticker, category, currency) VALUES ($1, $2, $3)",
            ticker, category, currency
        )
        await conn.execute(
            "INSERT INTO transactions (ticker, qty, price, date) VALUES ($1, $2, $3, $4)",
            ticker, qty, price, date
        )
        await conn.close()

        sign = "➕ Покупка" if qty > 0 else "➖ Продажа"
        response = (
            f"✅ Сделка добавлена\n\n"
            f"*{ticker}* | {sign}\n"
            f"{abs(qty)} шт × {price:.2f} {currency}\n"
            f"📅 Дата: {date}"
        )
        await query.edit_message_text(f"📂 Категория выбрана: {category}")
        await query.message.reply_text(response, parse_mode="Markdown")
