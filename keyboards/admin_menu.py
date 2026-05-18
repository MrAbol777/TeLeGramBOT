from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def build_admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ افزودن کانفیگ")],
            [KeyboardButton(text="📊 آمار موجودی")],
            [KeyboardButton(text="📊 آمار کلی")],
            [KeyboardButton(text="📈 گزارش فروش")],
            [KeyboardButton(text="📢 ارسال همگانی")],
            [KeyboardButton(text="💳 تنظیم شماره کارت")],
            [KeyboardButton(text="➕ افزودن کانفیگ جدید")],
            [KeyboardButton(text="💰 مدیریت قیمت‌ها")],
            [KeyboardButton(text="مدیریت سرویس‌ها")],
            [KeyboardButton(text="🔙 بازگشت به منوی اصلی")],
        ],
        resize_keyboard=True,
    )
