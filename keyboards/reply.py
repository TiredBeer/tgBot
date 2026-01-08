from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

helm_button = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📚 Выбрать курс")],
        [KeyboardButton(text="📝 Темы домашних заданий")],
        [KeyboardButton(text="ℹ️ Помощь")],
    ],
    resize_keyboard=True,
)

go_home = [[KeyboardButton(text="🏠 В главное меню")],]

send_or_select_topic = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Выбрать другую тему")],
        [KeyboardButton(text="Отправить задание")]
    ] + go_home,
    resize_keyboard=True
)