import asyncio
from sqlalchemy import select

from aiogram import Bot
from database.connect import async_session
from sqlalchemy.orm import selectinload
from database.models import SubmittedTaskOnChange, SubmittedTask, Task

async def alerts(bot: Bot, sleep: int = 1):
    while True:
        async with async_session() as session:
            result = await session.execute(
                select(SubmittedTaskOnChange)
                .options(
                    # сразу подтягиваем SubmittedTask и все нужные связи,
                    # чтобы потом не было ленивой загрузки
                    selectinload(SubmittedTaskOnChange.submitted_task)
                    .selectinload(SubmittedTask.task)
                    .selectinload(Task.teacher),
                    selectinload(SubmittedTaskOnChange.submitted_task)
                    .selectinload(SubmittedTask.status),
                    selectinload(SubmittedTaskOnChange.submitted_task)
                    .selectinload(SubmittedTask.student),
                )
                .order_by(SubmittedTaskOnChange.id)
                .limit(25)
            )
            changes = result.scalars().all()

            if not changes:
                await asyncio.sleep(sleep)
                continue

            for change in changes:
                st = change.submitted_task
                if st is None:
                    # на всякий случай, если FK битый
                    await session.delete(change)
                    continue

                task = st.task
                student = st.student
                teacher = task.teacher

                text = (
                    f"Ваше задание по теме «{task.topic}» проверено.\n"
                    f"Оценка: {st.grade}\n"
                    f"Коммент: {st.comment}\n"
                    f"Преподаватель: {teacher.name} {teacher.telegram_nickname}\n)"
                )

                try:
                    await bot.send_message(
                        chat_id=student.telegram_id,
                        text=text,
                    )
                except Exception as e:
                    print(f"Не смог отправить сообщение {student.telegram_id}: {e}")

                # удаляем запись из очереди
                await session.delete(change)

            await session.commit()

        await asyncio.sleep(sleep)



async def run_periodic_task():
    await asyncio.create_task(alerts())


if __name__ == '__main__':
    asyncio.run(alerts())

