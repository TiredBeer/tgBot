from collections import defaultdict
from zoneinfo import ZoneInfo

from aiogram.fsm.context import FSMContext
from aiogram import Router, types, F, Bot
from aiogram.types import InputMediaDocument, BufferedInputFile

from database.models import Task
from handlers.globalСommands import cmd_help
from yandexAPI.loader import upload_all_or_none, get_files_by_mask
from database.request import save_submission_to_db, has_student_submitted, \
    get_task_by_id, get_last_work
from handlers.course import show_course_topics
from keyboards.reply import send_or_select_topic, back_to_topics_kb, skip_pdf_kb, skip_code_kb
from states.register import LessonSelect
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
    task = await get_task_by_id(task_id)
    submitted_task = await has_student_submitted(student_id, task_id)
    if not submitted_task:
        if task:
            await message.answer(
                f"Ты еще не отправлял решение задач по этой теме\n"
                f"📚 Тема: {task.topic}\n"
                f"🔗 Ссылка на задачи {task.task_link}\n"
                f"📅 Дедлайн: {task.deadline.strftime('%d.%m.%Y') if task.deadline else '—'}\n"
                f"👤 Преподаватель: {task.teacher.name} {task.teacher.telegram_nickname}\n"
            )
        else:
            await message.answer("Задание не найдено.")
    else:
        await print_task_information(
            message=message,
            state=state,
            task=task,
            is_new_load=True,
        )

    await message.answer("Что ты хочешь сделать дальше?",
                         reply_markup=send_or_select_topic)
    await state.set_state(LessonSelect.after_topic)


async def print_task_information(message: types.Message, state: FSMContext, task: Task, is_new_load):
    await message.answer(
        "Загрузка твоей работы, может занять некоторое время, подожди пожалуйста")
    data = await state.get_data()
    task_id = data["task_id"]
    student_id = data.get("student_id")
    last_work = await get_last_work(student_id, task_id)
    # last_verified_work = await get_last_verified_work(student_id, task_id)

    topic = last_work.task.topic
    deadline = last_work.task.deadline
    teacher_name = last_work.task.teacher.name
    tg_nick = last_work.task.teacher.telegram_nickname
    comment = last_work.comment
    status_name = last_work.status.name
    grade = last_work.grade

    ekb_tz = ZoneInfo("Asia/Yekaterinburg")
    last_sent_at = last_work.last_modified_date.astimezone(ekb_tz).strftime("%d.%m.%Y %H:%M")
    first_sent = last_work.submitted_date.astimezone(ekb_tz).strftime("%d.%m.%Y %H:%M")
    #last_sent_at = last_work.last_modified_date.strftime("%d.%m.%Y %H:%M")
    #first_sent = last_work.submitted_date.strftime("%d.%m.%Y %H:%M")

    text = (
        f"📚 Тема: {topic}\n"
        f"🔗 Ссылка на задачи {task.task_link}\n"
        f"📅 Дедлайн: {deadline.strftime('%d.%m.%Y')}\n"
        f"👤 Преподаватель: {teacher_name}  {tg_nick}\n"
        f"📌 Статус: {status_name}\n"
        f"📨 Последняя отправка: {last_sent_at}\n"
        f"📬 Дата первой сдачи работы: {first_sent}\n"
    )

    # print(last_verified_work)
    if last_work.status_id == 1:
        # Рабрту проверили
        checking_messages = f"🟢 Твою работу проверили! 🟢\n📝 Оценка: {grade}\n"
        checking_messages += f"💬 Комментарий: {comment}\n\n" if comment else "\n"
        text = checking_messages + text
    elif last_work.submitted_date != last_work.last_modified_date and last_work.grade is not None:
        # last_work.status_id = 0, потому что мы уже отпарвли исправления на проверку, но старая оценка то есть
        refactor_massage = (
            "❗️ Исправления по заданию успешно отправлены.❗️\n"
            f"👉 Результаты проверки предыдущего решения:\n"
            f"📊 Оценка: {grade}\n"
        )
        refactor_massage += f"💬 Комментарий: {comment}\n\n" if comment else "\n"
        text = refactor_massage + text

    if last_work.code_url:
        text += f"💻 Ссылка на код: {last_work.code_url}\n"

    prefix = last_work.homework_prefix
    if prefix:
        files = await get_files_by_mask(prefix)
        await send_files_with_caption(files, message.bot, message.chat.id, text)
    elif last_work.code_url:
        await message.answer(text)
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


@router.message(LessonSelect.after_topic)
async def handle_reselect_topic(message: types.Message, state: FSMContext):
    if message.text == "Выбрать другую тему":
        data = await state.get_data()
        course_id = data.get("course_id")
        await show_course_topics(message, course_id, state)
        await state.set_state(LessonSelect.waiting_for_topic)
        return

    if message.text == "🏠 В главное меню":
        await cmd_help(message)
        return

    if message.text != "Отправить задание":
        await message.answer(
            "Выбери действие кнопкой 🙂",
            reply_markup=send_or_select_topic
        )
        await state.set_state(LessonSelect.after_topic)
        return

    # Отправить задание
    data = await state.get_data()
    task_id = data.get("task_id")
    if not task_id:
        await message.answer("Сначала выбери тему задания.")
        await state.set_state(LessonSelect.waiting_for_topic)
        return

    task = await get_task_by_id(task_id)

    if not task.need_code:
        await message.answer(
            "Отправь PDF одним сообщением.\n"
            "Если передумал — нажми «⬅️ К темам».",
            reply_markup=back_to_topics_kb
        )
        await state.set_state(LessonSelect.waiting_for_files)
        return

    await state.update_data(submitted_files=None, code_url=None)

    await message.answer(
        "На это задание можно отправть PDF или ссылку на Google Colab c кодом!\n\n"
        "Отправь PDF или пропусти этот шаг.",
        reply_markup=skip_pdf_kb
    )
    await state.set_state(LessonSelect.waiting_for_pdf_optional)


@router.message(LessonSelect.waiting_for_pdf_optional, F.text == "⬅️ К темам")
async def back_to_topics_from_pdf(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await show_course_topics(message, data.get("course_id"), state)
    await state.set_state(LessonSelect.waiting_for_topic)


@router.message(LessonSelect.waiting_for_pdf_optional, F.text == "⏭ Пропустить PDF")
async def skip_pdf(message: types.Message, state: FSMContext):
    await state.update_data(submitted_files=None)

    await message.answer(
        "Ок, PDF пропускаем.\n\n"
        "Пришли ссылку на код (Google Colab) или нажми «⏭️ Пропустить PDF».",
        reply_markup=skip_code_kb
    )
    await state.set_state(LessonSelect.waiting_for_code_url_optional)


@router.message(LessonSelect.waiting_for_pdf_optional, F.document)
async def take_optional_pdf(message: types.Message, state: FSMContext, bot: Bot):
    file_name = message.document.file_name.lower()
    if not file_name.endswith(".pdf"):
        await message.answer("На этом шаге принимаю только PDF или «⏭ Пропустить PDF».")
        return

    mask_prefix = await get_mask_for_save(state)
    files = [{
        "file_id": message.document.file_id,
        "original_file_name": message.document.file_name,
        "mask_for_save": mask_prefix
    }]

    ok = await upload_all_or_none(files, bot)
    if not ok:
        await message.answer("Не удалось загрузить PDF. Попробуй ещё раз или пропусти.")
        return

    await state.update_data(submitted_files=files)

    await message.answer(
        "PDF принят ✅\n\n"
        "Теперь пришли ссылку на код (Google Colab) или нажми «⏭ Пропустить ссылку».",
        reply_markup=skip_code_kb
    )
    await state.update_data(is_uploaded_file=True)
    await state.set_state(LessonSelect.waiting_for_code_url_optional)


@router.message(LessonSelect.waiting_for_pdf_optional)
async def reject_pdf_optional_other(message: types.Message):
    await message.answer("Отправь один PDF или нажми «⏭ Пропустить PDF».")


@router.message(LessonSelect.waiting_for_code_url_optional, F.text == "⬅️ К темам")
async def back_to_topics_from_code(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await show_course_topics(message, data.get("course_id"), state)
    await state.set_state(LessonSelect.waiting_for_topic)


@router.message(LessonSelect.waiting_for_code_url_optional, F.text == "⏭ Пропустить ссылку")
async def skip_code_url(message: types.Message, state: FSMContext):
    data = await state.get_data()
    files = data.get("submitted_files")
    code_url = data.get("code_url")

    if not files and not code_url:
        await message.answer(
            "Ты пропустил и PDF, и ссылку — значит ничего не отправил.\n"
            "Работа не сдана. Возвращаю к темам."
        )
        await show_course_topics(message, data.get("course_id"), state)
        await state.set_state(LessonSelect.waiting_for_topic)
        return

    await finalize_submission(message, state)


@router.message(LessonSelect.waiting_for_code_url_optional, F.text)
async def take_code_url(message: types.Message, state: FSMContext):
    url = message.text.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer("Пришли ссылку (http/https) или нажми «⏭ Пропустить ссылку».")
        return

    await state.update_data(code_url=url)
    await finalize_submission(message, state)


@router.message(LessonSelect.waiting_for_code_url_optional)
async def reject_code_other(message: types.Message):
    await message.answer("Пришли ссылку текстом или нажми «⏭ Пропустить ссылку».")


async def finalize_submission(message: types.Message, state: FSMContext):
    data = await state.get_data()
    student_id = data.get("student_id")
    task_id = data.get("task_id")
    code_url = data.get("code_url")
    is_uploaded_file = data.get("is_uploaded_file", False)
    mask_prefix = await get_mask_for_save(state) if is_uploaded_file else None
    await save_submission_to_db(student_id, task_id, mask_prefix, code_url=code_url)

    task = await get_task_by_id(task_id)
    await print_task_information(message, state, task, is_new_load=False)

    await message.answer("Готово ✅ Что дальше?", reply_markup=send_or_select_topic)
    await state.set_state(LessonSelect.after_topic)


@router.message(LessonSelect.waiting_for_files, F.text == "⬅️ К темам")
async def back_to_topics_from_files(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await show_course_topics(message, data.get("course_id"), state)
    await state.set_state(LessonSelect.waiting_for_topic)


@router.message(LessonSelect.waiting_for_files, F.document)
async def handle_get_single_file(message: types.Message, state: FSMContext):
    file_name = message.document.file_name.lower()
    if not file_name.endswith(".pdf"):
        await message.answer("Принимается только один файл формата .pdf. Попробуй ещё раз.")
        return

    mask_prefix = await get_mask_for_save(state)
    file = {
        "file_id": message.document.file_id,
        "original_file_name": message.document.file_name,
        "mask_for_save": mask_prefix
    }
    await after_accepting_files([file], message, state, mask_prefix)


@router.message(LessonSelect.waiting_for_files)
async def reject_non_files(message: types.Message):
    await message.answer("Пожалуйста, отправь **один PDF** или нажми «⬅️ К темам».")


async def after_accepting_files(files, message, state, mask_prefix):
    data = await state.get_data()
    student_id = data.get("student_id")
    task_id = data.get("task_id")
    code_url = data.get("code_url")
    bot = message.bot
    is_ok_load = await upload_all_or_none(files, bot)
    if is_ok_load:
        task = await get_task_by_id(task_id)
        await save_submission_to_db(student_id, task_id, mask_prefix, code_url=code_url)
        await state.update_data(submitted_files=files)
        await print_task_information(message, state, task, is_new_load=False)
        await message.answer("Что ты хочешь сделать дальше?",
                             reply_markup=send_or_select_topic)
        await state.set_state(LessonSelect.after_topic)
    else:
        await message.answer(
            "Во время загрузки произошли неполадки, отправь файлы пожалуйста еще раз")
        await state.set_state(LessonSelect.waiting_for_files)


@router.message(LessonSelect.waiting_for_files)
async def reject_non_files(message: types.Message):
    await message.answer("Пожалуйста, отправь файл формата .pdf")
