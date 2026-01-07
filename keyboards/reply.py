from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

lesson_actions_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Отправить домашку")],
        [KeyboardButton(text="Отправить дорешку")],
        [KeyboardButton(text="Отправить гробы")],
        [KeyboardButton(text="Выбрать другую тему")],
    ],
    resize_keyboard=True
)

cancel_files_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Я передумал, вернемся к выбору действий")],
    ],
    resize_keyboard=True
)
