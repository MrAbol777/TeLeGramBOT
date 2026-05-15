from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import settings
from database.db_handler import DatabaseHandler
from utils.states import RechargeStates

logger = logging.getLogger(__name__)

router = Router(name="user_menu")


def build_receipt_review_keyboard(user_id: int) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="تایید ✅",
            callback_data=f"approve_receipt:{user_id}",
        ),
        InlineKeyboardButton(
            text="رد ❌",
            callback_data=f"reject_receipt:{user_id}",
        ),
    )
    return builder


@router.callback_query(F.data == "user_profile")
async def user_profile_handler(
    callback: CallbackQuery,
    db: DatabaseHandler,
) -> None:
    await callback.answer()
    if callback.from_user is None:
        return

    user_id = callback.from_user.id

    try:
        await db.add_user_if_not_exists(user_id)
        balance = await db.get_user_balance(user_id)
    except Exception:
        logger.exception("Fetching user profile failed for user_id=%s", user_id)
        await callback.message.answer("❌ دریافت اطلاعات پروفایل با خطا مواجه شد.")
        return

    await callback.message.answer(
        f"👤 پروفایل شما\n"
        f"🆔 شناسه عددی: `{user_id}`\n"
        f"💰 موجودی کیف پول: `{balance:,}` تومان".replace(",", "٬"),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.in_({"recharge_wallet", "recharge"}))
async def recharge_wallet_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(RechargeStates.waiting_for_receipt)
    await callback.message.answer(
        "💳 برای شارژ حساب، مبلغ را به شماره کارت زیر واریز کنید:\n"
        f"`{settings.ADMIN_CARD_NUMBER}`\n\n"
        "📸 سپس عکس فیش واریزی را همین‌جا ارسال کنید.",
        parse_mode="Markdown",
    )


@router.message(RechargeStates.waiting_for_receipt, F.photo)
async def receipt_photo_handler(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db: DatabaseHandler,
) -> None:
    if message.from_user is None:
        return

    user = message.from_user
    caption_lines = [
        "📥 فیش جدید برای بررسی",
        f"🆔 شناسه کاربر: {user.id}",
    ]
    if user.username:
        caption_lines.append(f"👤 نام کاربری: @{user.username}")
    caption_lines.append("⚠️ یکی از گزینه‌های زیر را انتخاب کنید.")

    try:
        await db.add_user_if_not_exists(user.id)
        await bot.send_photo(
            chat_id=settings.ADMIN_ID,
            photo=message.photo[-1].file_id,
            caption="\n".join(caption_lines),
            reply_markup=build_receipt_review_keyboard(user.id).as_markup(),
        )
    except Exception:
        logger.exception("Forwarding receipt failed for user_id=%s", user.id)
        await message.answer("❌ ارسال فیش برای ادمین با خطا مواجه شد. دوباره تلاش کنید.")
        return

    await state.clear()
    await message.answer("✅ فیش شما دریافت شد و برای بررسی به ادمین ارسال شد.")


@router.message(RechargeStates.waiting_for_receipt)
async def invalid_receipt_handler(message: Message) -> None:
    await message.answer("⚠️ لطفاً فقط عکس فیش واریزی را ارسال کنید.")
