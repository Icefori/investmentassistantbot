import os
import nest_asyncio
import asyncio

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes, MessageHandler,
    CommandHandler, CallbackQueryHandler, filters
)

from handlers.deal import handle_deal, choose_category
from utils.portfolio import summarize_portfolio
from utils.formatter import send_markdown
from utils.parser import update_prices_json_from_portfolio
from bot.db import init_db, connect_db
from bot.utils.export import export_to_excel


BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN не найден. Установите переменную окружения.")

menu_keyboard = [
    ["📊 Мой портфель", "➕ Сделка"],
    ["💰 Дивиденды", "📰 Новости"],
    ["📤 Экспорт в Excel"]
]
reply_markup = ReplyKeyboardMarkup(menu_keyboard, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Выберите действие:", reply_markup=reply_markup)


async def show_all_deals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = await connect_db()
    rows = await conn.fetch("SELECT * FROM transactions ORDER BY date DESC")
    await conn.close()

    if not rows:
        await update.message.reply_text("📭 Сделок пока нет.")
        return

    text = "\n\n".join([
        f"*{r['ticker']}* | {r['qty']} шт × {r['price']:.2f} {r['currency']}\n📅 {r['date']}"
        for r in rows
    ])
    await update.message.reply_text(text, parse_mode="Markdown")


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text in ["📊 Мой портфель", "💰 Дивиденды", "📰 Новости", "⚙️ Настройки"]:
        context.user_data.pop("input_mode", None)

        if text == "📊 Мой портфель":
            await update_prices_json_from_portfolio()
            summary = await summarize_portfolio()
            await update.message.reply_text(summary, parse_mode="Markdown")
        else:
            await update.message.reply_text("🔔 Раздел в разработке. Ожидайте обновления.")
        return

    if text == "➕ Сделка":
        context.user_data["input_mode"] = "deals"
        await send_markdown(update,
            "📝 Введите сделки подряд.\n"
            "Формат: `Тикер Кол-во Цена [Валюта] [Дата]`\n"
            "Пример: `KZAP 10 17200`\n"
            "Нажмите любую кнопку, чтобы выйти из режима."
        )
        return

    if context.user_data.get("input_mode") == "deals":
        await handle_deal(update, context)
    


# ▶️ Запуск бота
if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(init_db())  # создаём таблицы

    async def main():
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("all_deals", show_all_deals))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
        app.add_handler(CallbackQueryHandler(choose_category))  # опционально, если включишь кнопки

        print("✅ Бот запускается через polling...")
        await app.run_polling()

    asyncio.run(main())
