from telegram import ReplyKeyboardMarkup

menu_keyboard = [
    ["📊 Мой портфель", "➕ Сделка"],
    ["💰 Дивиденды", "📰 Новости"],
    ["📤 Экспорт", "🧾 Расчет налогов"]
]
reply_markup = ReplyKeyboardMarkup(menu_keyboard, resize_keyboard=True)