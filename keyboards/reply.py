from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

send_or_select_topic = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Выбрать другую тему")],
        [KeyboardButton(text="Отправить задание")]
    ],
    resize_keyboard=True
)

helm_button = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📚 Выбрать курс")],
        [KeyboardButton(text="📝 Темы домашних заданий")],
        [KeyboardButton(text="ℹ️ Помощь")],
    ],
    resize_keyboard=True,
)