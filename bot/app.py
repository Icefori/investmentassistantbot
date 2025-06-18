import os
import nest_asyncio
import asyncio

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder, ContextTypes, MessageHandler,
    CommandHandler, CallbackQueryHandler, ConversationHandler, filters
)

from bot.handlers.deal import handle_deal, choose_category
from bot.handlers.portfolio import summarize_portfolio
from bot.utils.formatter import send_markdown
from bot.db import connect_db
from bot.utils.export import export_to_excel
from bot.handlers.taxes import export_taxes_excel
from bot.handlers.user import (
    is_registered, start_registration, ask_name, ask_timezone, ask_custom_timezone, finish_registration
)
from bot.utils.menu import reply_markup  # <-- импортируем кнопки из menu.py

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN не найден. Установите переменную окружения.")

# Этапы регистрации
ASK_NAME, ASK_TIMEZONE, ASK_CUSTOM_TIMEZONE = range(3)

# ConversationHandler для регистрации (без entry_points!)
registration_conv_handler = ConversationHandler(
    entry_points=[],  # теперь пусто!
    states={
        ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
        ASK_TIMEZONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_timezone)],
        ASK_CUSTOM_TIMEZONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_custom_timezone)],
    },
    fallbacks=[],
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Проверяем регистрацию пользователя
    if await is_registered(user_id):
        await update.message.reply_text(
            "👋 Добро пожаловать! Выберите действие из меню ниже:",
            reply_markup=reply_markup
        )
        return
    # Если не зарегистрирован — запускаем регистрацию
    return await start_registration(update, context)

# После успешной регистрации показываем меню (вызывается из finish_registration)
async def show_menu_after_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎉 Регистрация завершена! Теперь вы можете пользоваться всеми возможностями бота.\n\n"
        "Выберите действие из меню ниже:",
        reply_markup=reply_markup
    )

async def show_all_deals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = await connect_db()
    # Показываем только сделки текущего пользователя
    rows = await conn.fetch(
        "SELECT * FROM transactions WHERE user_id = $1 ORDER BY date DESC", user_id
    )
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
            summary = await summarize_portfolio(update, context)
            await update.message.reply_text(summary, parse_mode="Markdown")
        else:
            await update.message.reply_text("🔔 Раздел в разработке. Ожидайте обновления.")
        return

    if text == "➕ Сделка":
        context.user_data["input_mode"] = "deals"
        await send_markdown(update,
            "📝 Введите сделки подряд.\n"
            "Формат: `Тикер Кол-во Цена [Валюта] [Дата]`\n"
            "Пример:  `AAPL 10 150 USD 11-06-2025`\n"
            "Нажмите любую кнопку, чтобы выйти из режима."
        )
        return
    elif text == "📤 Экспорт":
        await export_to_excel(update, context)
    elif text == "🧾 Расчет налогов":
        context.user_data["input_mode"] = "taxes"
        await update.message.reply_text(
            "Пожалуйста, введите год для расчета налогов в формате YYYY (например, 2024):"
        )
        return

    # Обработка ввода года для налогов
    if context.user_data.get("input_mode") == "taxes":
        year_str = text.strip()
        if not (year_str.isdigit() and len(year_str) == 4):
            await update.message.reply_text("Введите год в формате YYYY, например: 2024")
            return
        year = int(year_str)
        await update.message.reply_text("⏳ Формируем налоговый отчет, это может занять до минуты...")
        await update.message.chat.send_action(action=ChatAction.UPLOAD_DOCUMENT)
        filename = await export_taxes_excel(year)
        with open(filename, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"Ваш налоговый отчет за {year} год"
            )
        context.user_data.pop("input_mode", None)
        return

    if context.user_data.get("input_mode") == "deals":
        await handle_deal(update, context)

# ▶️ Функция для запуска бота (используется в main.py)
async def run_bot():
    nest_asyncio.apply()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(registration_conv_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("all_deals", show_all_deals))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
    app.add_handler(CallbackQueryHandler(choose_category))  # опционально

    print("✅ Бот запускается через polling...")
    await app.run_polling()
