from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def build_user_purchases_keyboard(purchases: list[tuple[int, str, str, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for config_id, category, _config_content, sold_at in purchases:
        sold_at_simple = sold_at.replace("T", " ")[:16] if sold_at else "N/A"
        builder.button(
            text=f"{category} | {sold_at_simple}",
            callback_data=f"purchase_info:{config_id}",
        )
    builder.adjust(1)
    return builder.as_markup()
