import os
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

PORTFOLIO_PATH = "data/portfolio.json"
CATEGORIES_PATH = "data/categories.json"

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
                    await update.message.reply_text("❌ Ошибка: неверный формат даты. Используйте `дд-мм-гггг`", parse_mode="Markdown")
                    return

        if not os.path.exists(PORTFOLIO_PATH):
            with open(PORTFOLIO_PATH, "w", encoding="utf-8") as f:
                json.dump({}, f)

        with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
            portfolio = json.load(f)

        if ticker not in portfolio:
            context.user_data["pending_deal"] = {
                "ticker": ticker,
                "qty": qty,
                "price": price,
                "date": date,
                "currency": currency
            }

            await update.message.reply_text(f"🆕 Новый актив: {ticker}")

            if not currency:
                currency_markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton("KZT", callback_data="currency_KZT"),
                    InlineKeyboardButton("USD", callback_data="currency_USD"),
                    InlineKeyboardButton("EUR", callback_data="currency_EUR")
                ]])
                await update.message.reply_text("💱 Укажите валюту актива:", reply_markup=currency_markup)
            else:
                portfolio[ticker] = {
                    "category": "Unknown",
                    "currency": currency,
                    "transactions": []
                }
                with open(PORTFOLIO_PATH, "w", encoding="utf-8") as f:
                    json.dump(portfolio, f, indent=2, ensure_ascii=False)

            category_markup = InlineKeyboardMarkup([[
                InlineKeyboardButton("KZ", callback_data="category_KZ"),
                InlineKeyboardButton("ETF", callback_data="category_ETF"),
                InlineKeyboardButton("Gold", callback_data="category_Gold")
            ]])
            await update.message.reply_text("📂 Выберите категорию:", reply_markup=category_markup)
        else:
            portfolio[ticker]["transactions"].append({
                "qty": qty,
                "price": price,
                "date": date
            })
            with open(PORTFOLIO_PATH, "w", encoding="utf-8") as f:
                json.dump(portfolio, f, indent=2, ensure_ascii=False)

            sign = "➕ Покупка" if qty > 0 else "➖ Продажа"
            currency_display = portfolio[ticker]["currency"]
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
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("currency_"):
        currency = data.split("_")[1]
        pending = context.user_data.get("pending_deal")
        if not pending:
            await query.edit_message_text("⚠️ Нет ожидающей сделки.")
            return

        ticker = pending["ticker"]
        with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
            portfolio = json.load(f)

        portfolio[ticker] = {
            "category": "Unknown",
            "currency": currency,
            "transactions": []
        }

        with open(PORTFOLIO_PATH, "w", encoding="utf-8") as f:
            json.dump(portfolio, f, indent=2, ensure_ascii=False)

        await query.edit_message_text(f"💱 Валюта для *{ticker}* установлена: `{currency}`", parse_mode="Markdown")
        return

    if data.startswith("category_"):
        category = data.split("_")[1]
        pending = context.user_data.get("pending_deal")
        if not pending:
            await query.edit_message_text("⚠️ Нет ожидающей сделки.")
            return

        ticker = pending["ticker"]
        qty = pending["qty"]
        price = pending["price"]
        date = pending["date"]

        with open(PORTFOLIO_PATH, "r", encoding="utf-8") as f:
            portfolio = json.load(f)

        portfolio[ticker]["category"] = category
        portfolio[ticker]["transactions"].append({
            "qty": qty,
            "price": price,
            "date": date
        })

        with open(PORTFOLIO_PATH, "w", encoding="utf-8") as f:
            json.dump(portfolio, f, indent=2, ensure_ascii=False)

        if not os.path.exists(CATEGORIES_PATH):
            with open(CATEGORIES_PATH, "w", encoding="utf-8") as f:
                json.dump({}, f)

        with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
            categories = json.load(f)
        categories[ticker] = category
        with open(CATEGORIES_PATH, "w", encoding="utf-8") as f:
            json.dump(categories, f, indent=2, ensure_ascii=False)

        sign = "➕ Покупка" if qty > 0 else "➖ Продажа"
        currency_display = portfolio[ticker]["currency"]
        response = (
            f"✅ Сделка добавлена\\n\\n"
            f"*{ticker}* | {sign}\\n"
            f"{abs(qty)} шт × {price:.2f} {currency_display}\\n"
            f"📅 Дата: {date}"
        )

        await query.edit_message_text(f"📂 Категория для *{ticker}* установлена: `{category}`", parse_mode="Markdown")
        await query.message.reply_text(response, parse_mode="Markdown")
        context.user_data.pop("pending_deal", None)