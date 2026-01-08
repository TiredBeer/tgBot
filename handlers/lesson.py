import asyncio
from collections import defaultdict
from aiogram.fsm.context import FSMContext
from aiogram import Router, types, F, Bot
from aiogram.types import ReplyKeyboardRemove, InputMediaDocument, InputFile, \
    BufferedInputFile
from yandexAPI.loader import upload_all_or_none, get_files_by_mask
from database.request import get_last_verified_work, \
    get_task_id_by_topic_name, save_submission_to_db, has_student_submitted, \
    get_task_info_by_id, get_last_work
from handlers.course import show_course_topics
from keyboards.reply import send_or_select_topic
from states.register import LessonSelect, GravesSelect
from utils.auth import get_mask_for_save

router = Router()
album_cache: dict[str, list[types.Message]] = defaultdict(list)


@router.message(LessonSelect.waiting_for_topic)
async def handle_topic_selection(message: types.Message, state: FSMContext):
    data = await state.get_data()
    student_id = data.get("student_id")
    topic_name = message.text.strip()
    task_id = data.get("task_name_to_task_id", {}).get(topic_name, None)
    if not task_id:
        await message.answer("Такой темы нет. Выбери из списка.")
        return
    await state.update_data(task_id=task_id)
    await state.update_data(topic_name=topic_name)
    submitted_task = await has_student_submitted(student_id, task_id)
    if not submitted_task:
        task = await get_task_info_by_id(task_id)
        if task:
            await message.answer(
                f"Ты еще не отправлял домашнее задание по этой теме\n"
                f"📚 Тема: {task.topic}\n"
                f"📅 Дедлайн: {task.deadline.strftime('%d.%m.%Y') if task.deadline else '—'}\n"
                f"👤 Преподаватель: {task.teacher.name} {task.teacher.telegram_nickname}\n"
            )
        else:
            await message.answer("Задание не найдено.")
    else:
        await print_task_information(message, state)

    await message.answer("Что ты хочешь сделать дальше?",
                         reply_markup=send_or_select_topic)
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
    tg_nick = last_work.task.teacher.telegram_nickname
    comment = last_work.comment
    status_name = last_work.status.name
    grade = last_work.grade
    sent_at = last_work.submitted_date.strftime("%d.%m.%Y %H:%M")

    text = (
        "Вот твоя последняя отправленная работа\n"
        f"📚 Тема: {topic}\n"
        f"📅 Дедлайн: {deadline.strftime('%d.%m.%Y')}\n"
        f"👤 Преподаватель: {teacher_name}  {tg_nick}\n"
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


@router.message(LessonSelect.waiting_for_files, F.media_group_id)
async def handle_get_album(message: types.Message, state: FSMContext):
    media_group_id = str(message.media_group_id)
    data = await state.get_data()
    album_cache = data.get("media_group", {})

    album_cache.setdefault(media_group_id, []).append(message)
    await state.update_data(media_group=album_cache)

    # Ждём, пока Telegram пришлёт все части альбома
    await asyncio.sleep(1)

    # Повторно получаем данные
    data = await state.get_data()
    messages = data.get("media_group", {}).get(media_group_id, [])

    # Только последнее сообщение обрабатывает
    if message.message_id != messages[-1].message_id:
        return

    is_uncorrected_files = False
    files = []
    mask_prefix = await get_mask_for_save(state)
    for msg in messages:
        if msg.document:
            file_name = msg.document.file_name.lower()
            if file_name.endswith(".pdf") or file_name.endswith(".py"):
                files.append({
                    "file_id": msg.document.file_id,
                    "original_file_name": msg.document.file_name,
                    "mask_for_save": mask_prefix
                })
            else:
                is_uncorrected_files = True
                break
    if is_uncorrected_files:
        await message.answer(
            "Ты отправил недопустимые файлы. Принимаются только .pdf и .py. Попробуй еще раз.")
        return

    await after_accepting_files(files, message, state, mask_prefix)


@router.message(LessonSelect.waiting_for_files, F.document)
async def handle_get_single_file(message: types.Message, state: FSMContext):
    file_name = message.document.file_name.lower()
    if not (file_name.endswith(".pdf") or file_name.endswith(".py")):
        await message.answer(
            "Ты отправил недопустимые файл. Принимаются только .pdf и .py. Попробуй еще раз.")
        return
    mask_prefix = await get_mask_for_save(state)
    file = {
        "file_id": message.document.file_id,
        "original_file_name": message.document.file_name,
        "mask_for_save": mask_prefix
    }
    await after_accepting_files([file], message, state, mask_prefix)


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
                             reply_markup=send_or_select_topic)
        await state.set_state(LessonSelect.after_topic)
    else:
        await message.answer(
            "Во время загрузки произошли неполадки, отправь файлы пожалуйста еще раз")
        await state.set_state(LessonSelect.waiting_for_files)


@router.message(LessonSelect.waiting_for_files)
async def reject_non_files(message: types.Message):
    await message.answer("Пожалуйста, отправь файл формата .pdf или .py.")
