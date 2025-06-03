# utils/formatter.py

from telegram import Update

async def send_markdown(update: Update, text: str):
    await update.message.reply_text(text, parse_mode="Markdown")
