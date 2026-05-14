import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import settings
from database.db_handler import DatabaseHandler
from handlers import start

async def main():
    # تنظیمات لاگ (برای دیدن اتفاقات در کنسول)
    logging.basicConfig(level=logging.INFO)

    # راه اندازی دیتابیس
    db = DatabaseHandler("database.db")
    await db.initialize()

    # راه اندازی ربات
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    # ثبت روترها (هندلرها)
    dp.include_router(start.router)

    # وصل کردن دیتابیس به تمام هندلرها
    dp["db"] = db

    print("--- Bot is Running ---")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
