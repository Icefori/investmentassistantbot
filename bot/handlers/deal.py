import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from bot.db import connect_db
from bot.utils.fees import calc_fees

CURRENCY_CODES = {"KZT", "USD", "EUR", "RUB", "GBP", "CHF", "JPY", "CNY"}
EXCHANGES = ["KASE", "AIX", "NASDAQ", "AMEX", "LSE", "Другая"]
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID")

def escape_md(text):
    if text is None:
        return ""
    text = str(text)
    # Для обычного Markdown экранируем только *, _, `
    for ch in ('*', '_', '`'):
        text = text.replace(ch, f'\\{ch}')
    return text

async def handle_deal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id  # Получаем user_id
        message = update.message.text.strip()
        parts = message.split()

        if len(parts) < 3:
            await update.message.reply_text(
                "❗ Недостаточно данных. Введите: тикер, количество и цену.\n\n"
                "Пример: `AAPL 10 150 USD 11-06-2025`",
                parse_mode="MarkdownV2"
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
                        parse_mode="MarkdownV2"
                    )
                    return

        conn = await connect_db()
        # Теперь ищем тикер только среди активов этого пользователя
        row = await conn.fetchrow("SELECT * FROM portfolio WHERE ticker = $1 AND user_id = $2", ticker, user_id)
        await conn.close()

        if row is None:
            # Новый тикер: спросить валюту и категорию
            context.user_data["pending_deal"] = {
                "ticker": ticker,
                "qty": qty,
                "price": price,
                "date": date,
                "currency": currency,
                "user_id": user_id
            }
            await update.message.reply_text(f"🆕 Новый актив: {escape_md(ticker)}", parse_mode="MarkdownV2")

            if not currency:
                buttons = [
                    [InlineKeyboardButton("KZT", callback_data="currency_KZT"),
                     InlineKeyboardButton("USD", callback_data="currency_USD")]
                ]
                await update.message.reply_text("💱 Выберите валюту:", reply_markup=InlineKeyboardMarkup(buttons))
            else:
                await ask_category(update)
            return

        # Тикер уже есть у этого пользователя: берем валюту и категорию из portfolio
        context.user_data["pending_deal"] = {
            "ticker": ticker,
            "qty": qty,
            "price": price,
            "date": date,
            "currency": row["currency"],
            "category": row["category"],
            "user_id": user_id
        }
        await ask_exchange(update)
        return

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {escape_md(str(e))}", parse_mode="MarkdownV2")

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
            await query.edit_message_text("⚠️ Нет ожидающей сделки.", parse_mode="MarkdownV2")
            return
        pending["currency"] = currency
        await query.edit_message_text(f"💱 Валюта выбрана: {escape_md(currency)}", parse_mode="MarkdownV2")
        await ask_category(query)

    elif data.startswith("category_"):
        category = data.split("_")[1]
        pending = context.user_data.get("pending_deal")
        if not pending:
            await query.edit_message_text("⚠️ Нет ожидающей сделки.", parse_mode="MarkdownV2")
            return

        pending["category"] = category
        await query.edit_message_text(f"📂 Категория выбрана: {escape_md(category)}", parse_mode="MarkdownV2")
        await ask_exchange(query)

    elif data.startswith("exchange_"):
        exchange = data.split("_", 1)[1]
        pending = context.user_data.get("pending_deal")
        if not pending:
            await query.edit_message_text("⚠️ Нет ожидающей сделки.", parse_mode="MarkdownV2")
            return

        if exchange == "Другая":
            pending["awaiting_custom_exchange"] = True
            await query.edit_message_text("✍️ Введите название биржи текстом:", parse_mode="MarkdownV2")
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
        await _send_deal_message(update_or_query, "⚠️ Нет ожидающей сделки.", context)
        return

    user_id = pending.get("user_id")
    ticker = pending.get("ticker")
    qty = pending.get("qty")
    price = pending.get("price")
    date = pending.get("date")
    currency = pending.get("currency")
    exchange = pending.get("exchange")
    category = pending.get("category")

    # Проверяем, что все обязательные поля заполнены
    if not all([ticker, qty is not None, price is not None, date, currency, exchange, category, user_id]):
        logging.warning(f"[DEAL] Не все параметры заполнены: {pending}")
        await _send_deal_message(update_or_query, "⚠️ Не все параметры сделки заполнены. Проверьте ввод.", context)
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
        # Добавляем в portfolio если новый актив для этого пользователя
        await conn.execute(
            "INSERT INTO portfolio (ticker, category, currency, user_id) VALUES ($1, $2, $3, $4) "
            "ON CONFLICT (ticker, user_id) DO NOTHING",
            ticker, category, currency, user_id
        )
        # Добавляем сделку в transactions с user_id
        result = await conn.execute(
            "INSERT INTO transactions (ticker, qty, price, date, exchange, br_fee, ex_fee, cp_fee, sum, end_pr, user_id) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)",
            ticker, qty, price, date, exchange, br_fee, ex_fee, cp_fee, sum_value, end_pr, user_id
        )
        # Проверяем, что тикер теперь есть у пользователя
        portfolio_row = await conn.fetchrow("SELECT * FROM portfolio WHERE ticker = $1 AND user_id = $2", ticker, user_id)
        transaction_row = await conn.fetchrow(
            "SELECT * FROM transactions WHERE ticker = $1 AND qty = $2 AND price = $3 AND date = $4 AND user_id = $5",
            ticker, qty, price, date, user_id
        )
        await conn.close()
    except Exception as e:
        logging.error(f"[DEAL] Ошибка при добавлении сделки: {e}")
        await _send_deal_message(update_or_query, f"❌ Ошибка при добавлении сделки: {escape_md(str(e))}", context)
        return

    # Проверяем, что запись действительно добавлена и user_id совпадает
    if not (result and "INSERT" in result and portfolio_row and transaction_row and portfolio_row["user_id"] == user_id and transaction_row["user_id"] == user_id):
        logging.error(f"[DEAL] Сделка не была записана в базу данных: {ticker}, qty={qty}, price={price}, date={date}, currency={currency}, exchange={exchange}, category={category}, user_id={user_id}")
        await _send_deal_message(update_or_query, "❌ Сделка не была записана в базу данных.", context)
        return

    sign = "➕ Покупка" if qty > 0 else "➖ Продажа"
    response = (
        f"✅ Сделка добавлена\n\n"
        f"{escape_md(ticker)} | {escape_md(sign)}\n"
        f"{escape_md(abs(qty))} шт × {escape_md(f'{price:.2f}')} {escape_md(currency)}\n"
        f"Биржа: {escape_md(exchange)}\n"
        f"📅 Дата: {escape_md(date)}"
    )
    await _send_deal_message(update_or_query, response, context)

async def _send_deal_message(update_or_query, text, context=None):
    # Универсальная отправка сообщения пользователю
    user_id = None
    if hasattr(update_or_query, "from_user"):
        user_id = update_or_query.from_user.id
    elif hasattr(update_or_query, "message") and hasattr(update_or_query.message, "chat_id"):
        user_id = update_or_query.message.chat_id
    elif hasattr(update_or_query, "effective_user"):
        user_id = update_or_query.effective_user.id

    # fallback на OWNER_CHAT_ID из env
    if not user_id and OWNER_CHAT_ID:
        user_id = int(OWNER_CHAT_ID)

    # context должен быть передан явно!
    if not context and hasattr(update_or_query, "application"):
        context = update_or_query.application

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
        elif hasattr(update_or_query, "message"):
            await update_or_query.message.reply_text(text, parse_mode="Markdown")
