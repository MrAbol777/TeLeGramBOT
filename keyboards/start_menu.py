from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def build_start_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.add(
        InlineKeyboardButton(
            text="خرید سرویس",
            callback_data="buy_service",
            custom_emoji_id="5829966475623928907",
        ),
        InlineKeyboardButton(
            text="حساب کاربری",
            callback_data="user_profile",
            custom_emoji_id="5372926953978341366",
        ),
        InlineKeyboardButton(
            text="ثبت تیکت",
            callback_data="open_ticket",
            custom_emoji_id="5893480314558222431",
        ),
        InlineKeyboardButton(
            text="ارتباط با پشتیبانی",
            callback_data="support",
            custom_emoji_id="5875178591326573705",
        ),
        InlineKeyboardButton(
            text="شارژ حساب",
            callback_data="recharge",
            custom_emoji_id="5868268899480375540",
        ),
    )
    builder.adjust(2)

    return builder.as_markup()
