from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def build_admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ افزودن کانفیگ")],
            [KeyboardButton(text="📊 آمار موجودی")],
            [KeyboardButton(text="🔙 بازگشت به منوی اصلی")],
        ],
        resize_keyboard=True,
    )
