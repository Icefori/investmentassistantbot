from telegram import ReplyKeyboardMarkup

menu_keyboard = [
    ["📊 Мой портфель", "➕ Сделка", "📤 Экспорт"]
]
reply_markup = ReplyKeyboardMarkup(menu_keyboard, resize_keyboard=True)