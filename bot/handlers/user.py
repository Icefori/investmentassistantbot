from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from bot.db import connect_db

ASK_NAME, ASK_TIMEZONE, ASK_CUSTOM_TIMEZONE = range(3)

TIMEZONES = [
    "Астана", "Москва", "Амстердам", "Другая зона"
]
TIMEZONE_MAP = {
    "Астана": "+6",
    "Москва": "+3",
    "Амстердам": "+1"
}

# Импортируем меню из menu.py для повторного использования
from bot.utils.menu import reply_markup

async def is_registered(user_id: int) -> bool:
    conn = await connect_db()
    user = await conn.fetchrow("SELECT 1 FROM users WHERE user_id = $1", user_id)
    await conn.close()
    return user is not None

async def start_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = await connect_db()
    user = await conn.fetchrow("SELECT 1 FROM users WHERE user_id = $1", user_id)
    await conn.close()
    if user:
        # Уже зарегистрирован — показываем меню
        await update.message.reply_text(
            "👋 Добро пожаловать! Выберите действие из меню ниже:",
            reply_markup=reply_markup
        )
        return ConversationHandler.END
    await update.message.reply_text(
        "👋 Добро пожаловать в инвестиционного помощника!\n\n"
        "Пожалуйста, напишите, как я могу к вам обращаться? (Введите ваше имя) 😊",
        reply_markup=ReplyKeyboardRemove()
    )
    return ASK_NAME

async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name or len(name) > 30:
        await update.message.reply_text(
            "Пожалуйста, введите корректное имя (до 30 символов), чтобы я мог обращаться к вам лично 😊"
        )
        return ASK_NAME
    context.user_data["name"] = name
    kb = [[tz] for tz in TIMEZONES]
    await update.message.reply_text(
        f"Спасибо, {name}! 🙏\n\n"
        "Теперь выберите ваш часовой пояс для корректной работы напоминаний и уведомлений.\n"
        "Пожалуйста, выберите один из вариантов ниже или выберите 'Другая зона', если вашего города нет в списке:",
        reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
    )
    return ASK_TIMEZONE

async def ask_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz = update.message.text.strip()
    if tz not in TIMEZONES:
        await update.message.reply_text(
            "Пожалуйста, выберите часовой пояс из предложенного списка или выберите 'Другая зона'."
        )
        return ASK_TIMEZONE
    if tz == "Другая зона":
        await update.message.reply_text(
            "Пожалуйста, укажите ваш часовой пояс в формате GMT, например: +5 или -11.\n"
            "Будьте внимательны: используйте только цифры со знаком плюс или минус."
        )
        return ASK_CUSTOM_TIMEZONE
    context.user_data["timezone"] = TIMEZONE_MAP[tz]
    return await finish_registration(update, context)

async def ask_custom_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz = update.message.text.strip()
    if not (tz.startswith("+") or tz.startswith("-")) or not tz[1:].isdigit():
        await update.message.reply_text(
            "Пожалуйста, введите корректный часовой пояс, например: +5 или -11."
        )
        return ASK_CUSTOM_TIMEZONE
    context.user_data["timezone"] = tz
    return await finish_registration(update, context)

async def finish_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    name = context.user_data.get("name")
    timezone = context.user_data.get("timezone")
    conn = await connect_db()
    await conn.execute(
        "INSERT INTO users (user_id, username, name, timezone) VALUES ($1, $2, $3, $4)",
        user_id, username, name, timezone
    )
    await conn.close()
    await update.message.reply_text(
        f"🎉 Спасибо, {name}! Вы успешно зарегистрированы.\n"
        f"Ваш выбранный часовой пояс: GMT{timezone}\n\n"
        "Теперь вы можете пользоваться всеми возможностями инвестиционного помощника! 🚀",
        reply_markup=reply_markup
    )
    return ConversationHandler.END