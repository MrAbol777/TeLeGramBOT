from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def get_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="وضعیت فعلی"), KeyboardButton(text="چک کردن الان")],
            [KeyboardButton(text="تنظیم فاصله زمانی"), KeyboardButton(text="آخرین خطا")],
            [KeyboardButton(text="تست آنلاین بودن (Deep Link)")],
        ],
        resize_keyboard=True,
    )
