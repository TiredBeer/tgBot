import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN, ALERT_TIME
from utils.auth import AuthMiddleware
from handlers import globalСommands, lesson, rolllback, course
from utils.alerts import alerts

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(AuthMiddleware())
    dp.include_router(globalСommands.router)
    dp.include_router(lesson.router)
    dp.include_router(course.router)
    dp.include_router(rolllback.router)

    asyncio.create_task(alerts(bot, sleep=ALERT_TIME))

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
