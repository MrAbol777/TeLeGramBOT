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


def build_model_selection_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    plus_payload = {
        "text": "💎• Nox Plus",
        "callback_data": "buy_model:nox_plus",
        "icon_custom_emoji_id": "5875306327948923856",
    }
    multi_payload = {
        "text": "🍽• Nox Multi",
        "callback_data": "buy_model:nox_multi",
        "icon_custom_emoji_id": "5920303364574285697",
    }

    try:
        plus_button = InlineKeyboardButton(**plus_payload)
    except TypeError:
        plus_button = InlineKeyboardButton(
            text=plus_payload["text"],
            callback_data=plus_payload["callback_data"],
        )

    try:
        multi_button = InlineKeyboardButton(**multi_payload)
    except TypeError:
        multi_button = InlineKeyboardButton(
            text=multi_payload["text"],
            callback_data=multi_payload["callback_data"],
        )

    builder.row(plus_button)
    builder.row(multi_button)
    builder.row(InlineKeyboardButton(text="❌ انصراف", callback_data="cancel_purchase_flow"))
    return builder.as_markup()


def build_model_configs_menu(
    model: str,
    configs: list[tuple[int, str, int, str]],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for config_id, title, price, duration in configs:
        button_text = (
            f"📦 {title}\n"
            f"💰 {price:,} | ⏳ {duration}"
        ).replace(",", "٬")
        builder.row(
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"buy_config:{config_id}",
            )
        )

    if total_pages > 1:
        nav_row: list[InlineKeyboardButton] = []
        if page > 1:
            nav_row.append(
                InlineKeyboardButton(
                    text="⬅️ قبلی",
                    callback_data=f"buy_model_page:{model}:{page-1}",
                )
            )
        nav_row.append(
            InlineKeyboardButton(
                text=f"{page}/{total_pages}",
                callback_data="noop",
            )
        )
        if page < total_pages:
            nav_row.append(
                InlineKeyboardButton(
                    text="بعدی ➡️",
                    callback_data=f"buy_model_page:{model}:{page+1}",
                )
            )
        builder.row(*nav_row)

    builder.row(InlineKeyboardButton(text="❌ انصراف", callback_data="cancel_purchase_flow"))
    return builder.as_markup()


def build_model_purchase_confirmation_menu(config_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ خرید", callback_data=f"confirm_purchase:{config_id}"),
        InlineKeyboardButton(text="❌ انصراف", callback_data="cancel_purchase_flow"),
    )
    return builder.as_markup()
