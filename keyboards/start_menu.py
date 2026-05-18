from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def build_start_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="🛍 خرید سرویس",
            callback_data="buy_service",
        ),
        InlineKeyboardButton(
            text="🧑‍💻 حساب کاربری",
            callback_data="user_profile",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="📚 راهنمای اتصال",
            callback_data="connection_guide",
        ),
        InlineKeyboardButton(
            text="👨‍💻 پشتیبانی",
            callback_data="support",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="💳 شارژ حساب",
            callback_data="recharge_wallet",
        ),
        InlineKeyboardButton(
            text="📂 سرویس‌های من",
            callback_data="my_services",
        ),
    )
    return builder.as_markup()
