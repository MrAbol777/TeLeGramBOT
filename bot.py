import asyncio
import logging
from aiogram import Bot, Dispatcher
from config import settings
from database.db_handler import DatabaseHandler
from handlers import admin, start, user_menu

async def main():
    # تنظیمات لاگ (برای دیدن اتفاقات در کنسول)
    logging.basicConfig(level=logging.INFO)

    # راه اندازی دیتابیس
    db = DatabaseHandler("database.db")
    await db.initialize()
    # مقدار اولیه شماره کارت را یک بار از env داخل دیتابیس ثبت می‌کنیم.
    current_card = await db.get_setting("admin_card_number")
    if not current_card:
        await db.set_setting("admin_card_number", settings.ADMIN_CARD_NUMBER)

    # راه اندازی ربات
    bot = Bot(token=settings.BOT_TOKEN)
    dp = Dispatcher()

    # ثبت روترها (هندلرها)
    dp.include_router(start.router)
    dp.include_router(user_menu.router)
    dp.include_router(admin.router)

    # وصل کردن دیتابیس به تمام هندلرها
    dp["db"] = db

    print("--- Bot is Running ---")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
