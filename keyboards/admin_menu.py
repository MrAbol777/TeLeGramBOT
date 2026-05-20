from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


def build_admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="مدیریت سرویس‌ها")],
            [KeyboardButton(text="📊 آمار موجودی")],
            [KeyboardButton(text="📊 آمار کلی")],
            [KeyboardButton(text="📊 گزارش فروش")],
            [KeyboardButton(text="💳 مدیریت پرداخت")],
            [KeyboardButton(text="💱 مدیریت ولت‌های ارزی")],
            [KeyboardButton(text="📢 ارسال همگانی")],
            [KeyboardButton(text="📥 درخواست‌های شارژ")],
            [KeyboardButton(text="📊 گزارش شارژ")],
            [KeyboardButton(text="🚪 خروج از پنل مدیریت")],
        ],
        resize_keyboard=True,
    )
