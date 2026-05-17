from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def build_categories_buy_menu(categories: list[tuple[int, str, int, int]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for category_id, name, price, stock_count in categories:
        builder.add(
            InlineKeyboardButton(
                text=f"{name} - {price:,} تومان ({stock_count} موجود)".replace(",", "٬"),
                callback_data=f"buy_category:{category_id}",
            )
        )

    builder.add(
        InlineKeyboardButton(
            text="انصراف ❌",
            callback_data="cancel_purchase_flow",
        )
    )
    builder.adjust(1)
    return builder.as_markup()


def build_purchase_confirmation_menu(category_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="تایید خرید ✅",
            callback_data=f"confirm_purchase:{category_id}",
        ),
        InlineKeyboardButton(
            text="انصراف ❌",
            callback_data="cancel_purchase_flow",
        ),
    )
    return builder.as_markup()


def build_recharge_prompt_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="شارژ حساب 💳",
            callback_data="recharge_wallet",
        ),
        InlineKeyboardButton(
            text="انصراف ❌",
            callback_data="cancel_purchase_flow",
        ),
    )
    return builder.as_markup()


def build_admin_category_price_menu(categories: list[tuple[int, str, int, int]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for category_id, name, price, stock_count in categories:
        builder.add(
            InlineKeyboardButton(
                text=f"{name} | {price:,} تومان | {stock_count} موجود".replace(",", "٬"),
                callback_data=f"admin_price_category:{category_id}",
            )
        )

    builder.adjust(1)
    return builder.as_markup()
