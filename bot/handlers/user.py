from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from bot.db import connect_db
import pytz
from datetime import datetime
import re
import aiohttp

from geopy.geocoders import Nominatim
from timezonefinder import TimezoneFinder

ASK_NAME, ASK_TIMEZONE, ASK_CUSTOM_TIMEZONE = range(3)

TIMEZONES = [
    "Астана", "Москва", "Амстердам", "Другая зона"
]
CITY_TZ = {
    "Астана": "Asia/Almaty",
    "Москва": "Europe/Moscow",
    "Амстердам": "Europe/Amsterdam"
}

from bot.utils.menu import reply_markup

GEONAMES_USERNAME = "icefori"  # замените на свой username на geonames.org

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
    if not name or len(name) < 3 or len(name) > 30 or not re.match(r"^[A-Za-zА-Яа-яЁё\s\-]+$", name):
        await update.message.reply_text(
            "Пожалуйста, введите корректное имя (от 3 до 30 букв, без цифр и специальных символов)."
        )
        return ASK_NAME
    context.user_data["name"] = name
    kb = [[tz] for tz in TIMEZONES]
    await update.message.reply_text(
        f"Спасибо, {name}! 🙏\n\n"
        "Теперь выберите ваш город/часовой пояс для корректной работы напоминаний и уведомлений.\n"
        "Пожалуйста, выберите один из вариантов ниже или выберите 'Другая зона', если вашего города нет в списке:",
        reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
    )
    return ASK_TIMEZONE

async def ask_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz = update.message.text.strip()
    if tz not in TIMEZONES:
        await update.message.reply_text(
            "Пожалуйста, выберите город/часовой пояс из предложенного списка или выберите 'Другая зона'."
        )
        return ASK_TIMEZONE
    if tz == "Другая зона":
        await update.message.reply_text(
            "Пожалуйста, введите город, в котором вы живёте (например: Кокшетау, Караганда, Берлин, Нью-Йорк) или ближайший крупный город/столицу.\n"
            "Я автоматически определю ваш часовой пояс для корректных уведомлений."
        )
        return ASK_CUSTOM_TIMEZONE
    tz_name = CITY_TZ[tz]
    context.user_data["timezone"] = tz_name
    return await finish_registration(update, context)

async def ask_custom_timezone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tz_input = update.message.text.strip()
    # Сначала пробуем как pytz-таймзуна
    try:
        pytz.timezone(tz_input)
        context.user_data["timezone"] = tz_input
        return await finish_registration(update, context)
    except Exception:
        pass

    # Пробуем найти по названию города через geopy (на любом языке)
    geolocator = Nominatim(user_agent="investmentbot")
    location = None
    for lang in ["en", "ru", "uk"]:
        try:
            location = geolocator.geocode(tz_input, language=lang)
            if location:
                break
        except Exception:
            continue

    if location:
        lat, lng = location.latitude, location.longitude
        tf = TimezoneFinder()
        tz_found = tf.timezone_at(lng=lng, lat=lat)
        if tz_found:
            context.user_data["timezone"] = tz_found
            return await finish_registration(update, context)

    await update.message.reply_text(
        "❗ Не удалось распознать таймзону или город. Введите корректное название, например: Кокшетау, Кyiv, Astana, Караганда, Berlin, Europe/Berlin, Asia/Almaty, America/New_York."
    )
    return ASK_CUSTOM_TIMEZONE

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
        f"Ваш выбранный часовой пояс: {timezone}\n\n"
        "Теперь вы можете:\n"
        "• Добавлять сделки (кнопка ➕ Сделка)\n"
        "• Смотреть портфель (кнопка 📊 Мой портфель)\n"
        "• Экспортировать портфель в Excel (кнопка 📤 Экспорт)\n\n"
        "В будущем появятся новые функции и тарифы! 🚀",
        reply_markup=reply_markup
    )
    return ConversationHandler.END