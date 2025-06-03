
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes, MessageHandler,
    CommandHandler, CallbackQueryHandler, filters
)
from handlers.deal import handle_deal, choose_category
from utils.portfolio import summarize_portfolio
from utils.formatter import send_markdown
from utils.parser import update_prices_json_from_portfolio  # обновление цен

# 🔐 Загрузка токена (временно вручную)
BOT_TOKEN = "7889127674:AAHt4h9V0uWWCCk59uvQRs3vzOrlP8Ww328"

# 📋 Главное меню
menu_keyboard = [
    ["📊 Мой портфель", "➕ Сделка"],
    ["💰 Дивиденды", "📰 Новости"],
    ["⚙️ Настройки"]
]
reply_markup = ReplyKeyboardMarkup(menu_keyboard, resize_keyboard=True)

# 🚀 Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Выберите действие:", reply_markup=reply_markup)

# 🧠 Обработка всех сообщений
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    # ✅ Обработка кнопок
    if text in ["📊 Мой портфель", "💰 Дивиденды", "📰 Новости", "⚙️ Настройки"]:
        context.user_data.pop("input_mode", None)

        if text == "📊 Мой портфель":
            update_prices_json_from_portfolio()  # 🔄 Сначала обновим цены
            summary = summarize_portfolio()
            await update.message.reply_text(summary, parse_mode="Markdown")
        else:
            await update.message.reply_text("🔔 Раздел в разработке. Ожидайте обновления.")
        return

    # ➕ Вход в режим сделок
    if text == "➕ Сделка":
        context.user_data["input_mode"] = "deals"
        await send_markdown(update,
            "📝 Введите сделки подряд.\n"
            "Формат: `Тикер Кол-во Цена [Валюта] [Дата]`\n"
            "Пример: `KZAP 10 17200`\n"
            "Нажмите любую кнопку, чтобы выйти из режима."

        )
        return

    # 💼 Обработка сделок
    if context.user_data.get("input_mode") == "deals":
        await handle_deal(update, context)

# ▶️ Запуск бота
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    app.add_handler(CallbackQueryHandler(choose_category))

    print("Попытка запуска...")
    print("Бот запущен — ждём сообщения в Telegram!")
    app.run_polling()
