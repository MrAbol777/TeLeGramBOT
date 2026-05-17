from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def build_start_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.add(
        InlineKeyboardButton(
            text="🛍 خرید سرویس",
            callback_data="buy_service",
            custom_emoji_id="5829966475623928907",
        ),
        InlineKeyboardButton(
            text="👤 حساب کاربری",
            callback_data="user_profile",
            custom_emoji_id="5372926953978341366",
        ),
        InlineKeyboardButton(
            text="📚 راهنمای اتصال",
            callback_data="connection_guide",
        ),
        InlineKeyboardButton(
            text="👨‍💻 پشتیبانی",
            callback_data="support",
        ),
        InlineKeyboardButton(
            text="💳 شارژ حساب",
            callback_data="recharge_wallet",
            custom_emoji_id="5868268899480375540",
        ),
        InlineKeyboardButton(
            text="📂 سرویس‌های من",
            callback_data="my_services",
        ),
    )
    builder.adjust(2)

    return builder.as_markup()
