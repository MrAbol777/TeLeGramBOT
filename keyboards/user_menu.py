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
        InlineKeyboardButton(
            text="شارژ حساب",
            callback_data="recharge_wallet",
            icon_custom_emoji_id="5868268899480375540",
        ),
        InlineKeyboardButton(
            text="سرویس‌های من",
            callback_data="my_services_menu",
            icon_custom_emoji_id="5443127283898405358",
        ),
        InlineKeyboardButton(
            text="زیرمجموعه‌گیری",
            callback_data="referral_menu",
            icon_custom_emoji_id="5839449299557028781",
        ),
        InlineKeyboardButton(
            text="راهنمای اتصال",
            callback_data="connection_guide",
            icon_custom_emoji_id="5222444124698853913",
        ),
        InlineKeyboardButton(
            text="ارتباط با پشتیبانی",
            callback_data="support",
            icon_custom_emoji_id="5810032437186531403",
        ),
    )
    builder.adjust(2)
    return builder.as_markup()


def build_recharge_method_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    crypto_payload = {
        "text": "پرداخت ارزی",
        "callback_data": "recharge_method_crypto",
        "icon_custom_emoji_id": "5402186569006210455",
    }
    card_payload = {
        "text": "کارت به کارت",
        "callback_data": "recharge_method_card",
        "icon_custom_emoji_id": "5204242830687494041",
    }

    try:
        crypto_button = InlineKeyboardButton(**crypto_payload)
    except TypeError:
        crypto_button = InlineKeyboardButton(
            text=crypto_payload["text"],
            callback_data=crypto_payload["callback_data"],
        )

    try:
        card_button = InlineKeyboardButton(**card_payload)
    except TypeError:
        card_button = InlineKeyboardButton(
            text=card_payload["text"],
            callback_data=card_payload["callback_data"],
        )

    builder.row(crypto_button)
    builder.row(card_button)
    return builder.as_markup()
