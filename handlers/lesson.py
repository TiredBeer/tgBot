import asyncio
from collections import defaultdict
from aiogram.fsm.context import FSMContext
from aiogram import Router, types, F, Bot
from aiogram.types import InputMediaDocument, BufferedInputFile
from yandexAPI.loader import upload_all_or_none, get_files_by_mask
from database.request import get_last_verified_work, \
    get_task_id_by_topic_name, save_submission_to_db, has_student_submitted, \
    get_task_info_by_id, get_last_work
from handlers.course import show_course_topics
from keyboards.reply import lesson_actions_keyboard, cancel_files_keyboard
from states.register import LessonSelect
from utils.auth import get_mask_for_save

router = Router()
album_cache: dict[str, list[types.Message]] = defaultdict(list)


@router.message(LessonSelect.waiting_for_topic)
async def handle_topic_selection(message: types.Message, state: FSMContext):
    data = await state.get_data()
    tasks = data["tasks"]
    topic_name = message.text.strip()

    if topic_name not in tasks:
        await message.answer("Такой темы нет. Выбери из списка.")
        return

    # сохраняем только тему, тип выберем позже по кнопке
    await state.update_data(topic_name=topic_name)

    await message.answer(
        "Тема выбрана. Что именно хочешь отправить?",
        reply_markup=lesson_actions_keyboard
    )
    await state.set_state(LessonSelect.after_topic)



async def print_task_information(message: types.Message, state: FSMContext):
    await message.answer(
        "Загрузка твоей работы, может занять некоторое время, подожди пожалуйста")
    data = await state.get_data()
    task_id = data["task_id"]
    student_id = data.get("student_id")
    last_work = await get_last_work(student_id, task_id)
    last_verified_work = await get_last_verified_work(student_id, task_id)

    topic = last_work.task.topic
    deadline = last_work.task.deadline
    teacher_name = last_work.task.teacher.name
    telegram_nickname = last_work.task.teacher.telegram_nickname
    comment = last_work.comment
    status_name = last_work.status.name
    grade = last_work.grade
    sent_at = last_work.submitted_date.strftime("%d.%m.%Y %H:%M")

    text = (
        "Вот твоя последняя отправленная работа\n"
        f"📚 Тема: {topic}\n"
        f"📅 Дедлайн: {deadline.strftime('%d.%m.%Y')}\n"
        f"👤 Преподаватель: {teacher_name} {telegram_nickname}\n"
        f"📌 Статус: {status_name}\n"
        f"📨 Отправлено: {sent_at}\n"
    )

    print(last_verified_work)
    if status_name == "Проверено":
        text += f"📝 Оценка: {grade}\n💬 Комментарий: {comment}"
    elif grade != 0:
        text += (f"\nТвой предыдущая работа было оценена на {grade}\n"
             f"С комментарием: {comment}\n"
             f"Твоя новая работа отпарвлена на проверку"
        )

    prefix = last_work.homework_prefix
    files = await get_files_by_mask(prefix)
    if files:
        await send_files_with_caption(files, message.bot, message.chat.id, text)
    else:
        await message.answer("Технические неполадки, попробуй еще раз")


async def send_files_with_caption(
        files: list[dict], bot: Bot, chat_id: int, caption: str):
    await bot.send_message(chat_id=chat_id, text=caption)
    media = []
    for i, file in enumerate(files):
        buffer = file["buffer"]
        filename = file["filename"]

        input_file = BufferedInputFile(
            file=buffer.getvalue(),
            filename=filename
        )

        media_doc = InputMediaDocument(media=input_file)
        media.append(media_doc)

    await bot.send_media_group(chat_id=chat_id, media=media)


@router.message(LessonSelect.after_topic, F.text == "Выбрать другую тему")
async def handle_reselect_topic(message: types.Message, state: FSMContext):
    data = await state.get_data()
    course_id = data.get("course_id")
    await show_course_topics(message, course_id, state)
    await state.set_state(LessonSelect.waiting_for_topic)


@router.message(LessonSelect.after_topic, F.text == "Отправить задание")
async def handle_send_homework(message: types.Message, state: FSMContext):
    await message.answer("Отправь задание одним сообщением",
                         reply_markup=ReplyKeyboardRemove())
    await state.set_state(LessonSelect.waiting_for_files)


@router.message(LessonSelect.waiting_for_files, F.document, F.media_group_id)
async def handle_get_album(message: types.Message, state: FSMContext):
    group_id = str(message.media_group_id)
    album_cache[group_id].append(message)

    # ждём, пока телега дошлёт все части альбома
    await asyncio.sleep(1.0)

    messages = album_cache.pop(group_id, None)
    if not messages:
        return

    mask_prefix = await get_mask_for_save(state)
    files: list[dict] = []

    for msg in messages:
        doc = msg.document
        if not doc:
            continue

        file_name = doc.file_name.lower()
        if not (file_name.endswith(".pdf") or file_name.endswith(".py")):
            await message.answer(
                "Ты отправил недопустимые файлы. Принимаются только .pdf и .py. "
                "Попробуй еще раз."
            )
            return

        files.append(
            {
                "file_id": doc.file_id,
                "original_file_name": doc.file_name,
                "mask_for_save": mask_prefix,
            }
        )

    if not files:
        await message.answer("В альбоме не найдено подходящих файлов.")
        return

    await after_accepting_files(files, message, state, mask_prefix)


@router.message(LessonSelect.waiting_for_files, F.document, ~F.media_group_id)
async def handle_get_single_file(message: types.Message, state: FSMContext):
    file_name = message.document.file_name.lower()
    if not (file_name.endswith(".pdf") or file_name.endswith(".py")):
        await message.answer(
            "Ты отправил недопустимый файл. Принимаются только .pdf и .py. "
            "Попробуй еще раз."
        )
        return

    mask_prefix = await get_mask_for_save(state)
    file = {
        "file_id": message.document.file_id,
        "original_file_name": message.document.file_name,
        "mask_for_save": mask_prefix,
    }
    await after_accepting_files([file], message, state, mask_prefix)

from aiogram.types import ReplyKeyboardRemove

@router.message(LessonSelect.after_topic)
async def handle_after_topic(message: types.Message, state: FSMContext):
    text = message.text.strip()
    data = await state.get_data()
    student_id = data.get("student_id")
    course_id = data.get("course_id")
    topic_name = data.get("topic_name")

    # 1) выбрать другую тему
    if text == "Выбрать другую тему":
        await message.answer(
            "Выбери тему из списка:",
            reply_markup=ReplyKeyboardRemove()
        )
        # тут ты заново шлёшь список тем и:
        await state.set_state(LessonSelect.waiting_for_topic)
        return

    BUTTON_TO_TYPE = {
        "Отправить домашку": 0,
        "Отправить дорешку": 1,
        "Отправить гробы": 2,
    }
    # 2) отправить домашку / дорешку / гробы
    if text in BUTTON_TO_TYPE:
        task_type = BUTTON_TO_TYPE[text]

        # достаем нужную Task по теме + курсу + типу
        task_id = await get_task_id_by_topic_name(
            topic_name=topic_name,
            course_id=course_id,
            task_type=task_type,  # <--- важно!
        )

        if not task_id:
            await message.answer("Для этой темы и типа работы задание не найдено.")
            return

        await state.update_data(task_id=task_id, task_type=task_type)

        submitted_task = await has_student_submitted(student_id, task_id)

        if not submitted_task:
            task = await get_task_info_by_id(task_id)
            if task:
                await message.answer(
                    f"Ты еще не отправлял эту работу\n"
                    f"📚 Тема: {task.topic}\n"
                    f"📅 Дедлайн: {task.deadline.strftime('%d.%m.%Y') if task.deadline else '—'}\n"
                    f"👤 Преподаватель: {task.teacher.name} {task.teacher.telegram_nickname}\n"
                )
            else:
                await message.answer("Задание не найдено.")
        else:
            # тут можешь либо показать инфу, либо сразу предложить 'перезалить'
            await print_task_information(message, state)

        await message.answer(
            "Пришли файлы одним сообщением:",
            reply_markup=cancel_files_keyboard
        )
        await state.set_state(LessonSelect.waiting_for_files)
        return

    # 3) любой левый текст
    await message.answer(
        "Пожалуйста, выбери действие с кнопок ниже.",
        reply_markup=lesson_actions_keyboard
    )


@router.message(
    LessonSelect.waiting_for_files,
    F.text == "Я передумал, вернемся к выбору действий"
)
async def cancel_file_upload(message: types.Message, state: FSMContext):
    await message.answer(
        "Ок, возвращаемся к выбору действий.",
        reply_markup=lesson_actions_keyboard,
    )
    await state.set_state(LessonSelect.after_topic)


async def after_accepting_files(files, message, state, mask_prefix):
    data = await state.get_data()
    student_id = data.get("student_id")
    task_id = data.get("task_id")
    bot = message.bot
    is_ok_load = await upload_all_or_none(files, bot)
    if is_ok_load:
        await save_submission_to_db(student_id, task_id, mask_prefix)
        await state.update_data(submitted_files=files)
        await print_task_information(message, state)
        await message.answer("Что ты хочешь сделать дальше?",
                             reply_markup=lesson_actions_keyboard)
        await state.set_state(LessonSelect.after_topic)
    else:
        await message.answer(
            "Во время загрузки произошли неполадки, отправь файлы пожалуйста еще раз")
        await state.set_state(LessonSelect.waiting_for_files)


@router.message(
    LessonSelect.waiting_for_files,
    ~F.document,
    F.text != "Я передумал, вернемся к выбору действий"
)
async def reject_non_files(message: types.Message):
    await message.answer("Пожалуйста, отправь файл формата .pdf или .py.")
