from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from database.request import get_available_courses_for_student
from states.register import Lesson, CourseSelect, LessonSelect
from handlers.course import show_course_topics
from keyboards.reply import helm_button

router = Router()


@router.message(lambda m: m.text == "ℹ️ Помощь")
async def cmd_help(message: types.Message):
    await message.answer("Что делаем?", reply_markup=helm_button)

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer("Что делаем?", reply_markup=helm_button)


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет, я бот для отправок домашних работ и гробов по теории вероятности и математической статистике\n"
        "Узнать о моем функционале: /help",
        reply_markup = helm_button
    )


@router.message(lambda m: m.text == "📝 Темы домашних заданий")
async def get_lesson(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if "course_id" not in data:
        courses = await get_available_courses_for_student(message.from_user.id)

        if not courses:
            await message.answer(
                "У тебя нет доступных курсов. Обратись к преподавателю.")
            return

        course_map = {course.name: course.id for course in courses}
        await state.update_data(course_map=course_map)
        buttons = [[KeyboardButton(text=name)] for name in course_map.keys()]
        kb = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
        await message.answer("Ты ещё не выбрал курс. Выбери один из доступных:",
                             reply_markup=kb)
        await state.set_state(CourseSelect.waiting_for_course)
    else:
        course_id = data["course_id"]
        await show_course_topics(message, course_id, state)
        await state.set_state(LessonSelect.waiting_for_topic)


@router.message(lambda m: m.text == "📚 Выбрать курс")
async def get_my_course(message: types.Message, state: FSMContext):
    courses = await get_available_courses_for_student(message.from_user.id)

    if not courses:
        await message.answer(
            "У тебя пока нет доступных курсов. Обратись к преподавателю.")
        return

    course_map = {course.name: course.id for course in courses}
    await state.update_data(course_map=course_map)

    buttons = [[KeyboardButton(text=course.name)] for course in courses]
    kb = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

    await message.answer("Вот твои доступные курсы", reply_markup=kb)
    await state.set_state(CourseSelect.waiting_for_course)

