from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from bot.db import connect_db
from bot.utils.fees import calc_fees

CURRENCY_CODES = {"KZT", "USD", "EUR", "RUB", "GBP", "CHF", "JPY", "CNY"}
EXCHANGES = ["KASE", "AIX", "NASDAQ", "AMEX", "LSE", "Другая"]

async def handle_deal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message.text.strip()
        parts = message.split()

        if len(parts) < 3:
            await update.message.reply_text(
                "❗ Недостаточно данных. Введите: тикер, количество и цену.\n\n"
                "Пример: `AAPL 10 150 USD 11-06-2025`",
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
            # Новый тикер: спросить валюту и категорию
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

        # Тикер уже есть: берем валюту и категорию из portfolio
        context.user_data["pending_deal"] = {
            "ticker": ticker,
            "qty": qty,
            "price": price,
            "date": date,
            "currency": row["currency"],
            "category": row["category"]
        }
        await ask_exchange(update)
        return

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

async def ask_exchange(update_or_query):
    buttons = [
        [InlineKeyboardButton(ex, callback_data=f"exchange_{ex}")] for ex in EXCHANGES[:-1]
    ]
    buttons.append([InlineKeyboardButton("Другая", callback_data="exchange_Другая")])
    if hasattr(update_or_query, "message"):
        await update_or_query.message.reply_text("🌐 Выберите биржу:", reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update_or_query.message.reply_text("🌐 Выберите биржу:", reply_markup=InlineKeyboardMarkup(buttons))

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
        pending = context.user_data.get("pending_deal")
        if not pending:
            await query.edit_message_text("⚠️ Нет ожидающей сделки.")
            return

        pending["category"] = category
        await query.edit_message_text(f"📂 Категория выбрана: {category}")
        await ask_exchange(query)

    elif data.startswith("exchange_"):
        exchange = data.split("_", 1)[1]
        pending = context.user_data.get("pending_deal")
        if not pending:
            await query.edit_message_text("⚠️ Нет ожидающей сделки.")
            return

        if exchange == "Другая":
            pending["awaiting_custom_exchange"] = True
            await query.edit_message_text("✍️ Введите название биржи текстом:")
            return

        pending["exchange"] = exchange
        await finalize_deal(query, context)

async def handle_custom_exchange(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = context.user_data.get("pending_deal")
    if not pending or not pending.get("awaiting_custom_exchange"):
        return
    exchange = update.message.text.strip()
    pending["exchange"] = exchange
    pending.pop("awaiting_custom_exchange")
    await finalize_deal(update, context)

async def finalize_deal(update_or_query, context):
    pending = context.user_data.pop("pending_deal", None)
    if not pending:
        await _send_deal_message(update_or_query, "⚠️ Нет ожидающей сделки.")
        return

    ticker = pending.get("ticker")
    qty = pending.get("qty")
    price = pending.get("price")
    date = pending.get("date")
    currency = pending.get("currency")
    exchange = pending.get("exchange")
    category = pending.get("category")

    # Проверяем, что все обязательные поля заполнены
    if not all([ticker, qty is not None, price is not None, date, currency, exchange, category]):
        await _send_deal_message(update_or_query, "⚠️ Не все параметры сделки заполнены. Проверьте ввод.")
        return

    is_sell = qty < 0
    fees = calc_fees(exchange, abs(qty), price, is_sell)
    br_fee = fees["br_fee"]
    ex_fee = fees["ex_fee"]
    cp_fee = fees["cp_fee"]
    sum_value = fees["sum"]
    end_pr = fees["end_pr"]

    try:
        conn = await connect_db()
        # Добавляем в portfolio если новый актив
        await conn.execute(
            "INSERT INTO portfolio (ticker, category, currency) VALUES ($1, $2, $3) ON CONFLICT (ticker) DO NOTHING",
            ticker, category, currency
        )
        result = await conn.execute(
            "INSERT INTO transactions (ticker, qty, price, date, exchange, br_fee, ex_fee, cp_fee, sum, end_pr) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
            ticker, qty, price, date, exchange, br_fee, ex_fee, cp_fee, sum_value, end_pr
        )
        await conn.close()
    except Exception as e:
        await _send_deal_message(update_or_query, f"❌ Ошибка при добавлении сделки: {e}")
        return

    # Проверяем, что запись действительно добавлена (result должен содержать INSERT ...)
    if not (result and "INSERT" in result):
        await _send_deal_message(update_or_query, "❌ Сделка не была записана в базу данных.")
        return

    sign = "➕ Покупка" if qty > 0 else "➖ Продажа"
    response = (
        f"✅ Сделка добавлена\n\n"
        f"*{ticker}* | {sign}\n"
        f"{abs(qty)} шт × {price:.2f} {currency}\n"
        f"Биржа: {exchange}\n"
        f"Комиссии: br_fee={br_fee}, ex_fee={ex_fee}, cp_fee={cp_fee}\n"
        f"Сумма: {sum_value}\n"
        f"Цена с учетом комиссий: {end_pr}\n"
        f"📅 Дата: {date}"
    )
    await _send_deal_message(update_or_query, response)

async def _send_deal_message(update_or_query, text):
    # Универсальная отправка сообщения пользователю
    if hasattr(update_or_query, "from_user"):
        user_id = update_or_query.from_user.id
    elif hasattr(update_or_query, "message") and hasattr(update_or_query.message, "chat_id"):
        user_id = update_or_query.message.chat_id
    else:
        user_id = None

    context = update_or_query.application if hasattr(update_or_query, "application") else None
    if user_id and context:
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="Markdown"
        )
    else:
        # fallback на старое поведение
        if hasattr(update_or_query, "edit_message_text"):
            await update_or_query.edit_message_text(text, parse_mode="Markdown")
        else:
            await update_or_query.message.reply_text(text, parse_mode="Markdown")
