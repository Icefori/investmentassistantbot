from datetime import datetime
from telegram import Update
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

        # 1. Вставить в portfolio, если тикера нет
        await conn.execute(
            """
            INSERT INTO portfolio (ticker, category, currency)
            VALUES ($1, 'KZ', $2)
            ON CONFLICT (ticker) DO NOTHING
            """,
            ticker,
            currency or "KZT"
        )

        # 2. Добавить сделку
        await conn.execute(
            """
            INSERT INTO transactions (ticker, qty, price, date)
            VALUES ($1, $2, $3, $4)
            """,
            ticker, qty, price, date
        )

        await conn.close()

        sign = "➕ Покупка" if qty > 0 else "➖ Продажа"
        currency_display = currency or "KZT"
        response = (
            f"✅ Сделка добавлена\n\n"
            f"*{ticker}* | {sign}\n"
            f"{abs(qty)} шт × {price:.2f} {currency_display}\n"
            f"📅 Дата: {date}"
        )
        await update.message.reply_text(response, parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

async def choose_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Категории будут поддерживаться позже.")
