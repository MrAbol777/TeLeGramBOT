from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def build_main_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    buy_service_payload = {
        "text": "خرید سرویس",
        "callback_data": "buy_service",
        "icon_custom_emoji_id": "5829966475623928907",
    }
    try:
        buy_service_button = InlineKeyboardButton(**buy_service_payload)
    except TypeError:
        buy_service_button = InlineKeyboardButton(
            text=buy_service_payload["text"],
            callback_data=buy_service_payload["callback_data"],
        )

    account_button_payload = {
        "text": "حساب کاربری",
        "callback_data": "user_profile",
        "icon_custom_emoji_id": "5372926953978341366",
    }
    try:
        account_button = InlineKeyboardButton(**account_button_payload)
    except TypeError:
        account_button = InlineKeyboardButton(
            text=account_button_payload["text"],
            callback_data=account_button_payload["callback_data"],
        )

    builder.add(
        buy_service_button,
        account_button,
        InlineKeyboardButton(text="💳 شارژ حساب", callback_data="recharge_wallet"),
        InlineKeyboardButton(text="📂 سرویس‌های من", callback_data="my_services"),
        InlineKeyboardButton(text="👥 زیرمجموعه‌گیری", callback_data="referral_info"),
        InlineKeyboardButton(text="📚 راهنمای اتصال", callback_data="connection_guide"),
        InlineKeyboardButton(text="👨‍💻 پشتیبانی", callback_data="support"),
    )
    builder.adjust(2)
    return builder.as_markup()
