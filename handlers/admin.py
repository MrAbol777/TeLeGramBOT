from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import settings
from database.db_handler import DatabaseHandler
from keyboards.admin_menu import build_admin_menu
from keyboards.start_menu import build_start_menu
from utils.states import AdminRechargeStates

logger = logging.getLogger(__name__)

router = Router(name="admin")
router.message.filter(F.from_user.id == settings.ADMIN_ID)
router.callback_query.filter(F.from_user.id == settings.ADMIN_ID)


class AdminConfigStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_configs = State()


@router.message(Command("admin"))
async def admin_panel_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "پنل ادمین فعال شد. یکی از گزینه‌های زیر را انتخاب کنید.",
        reply_markup=build_admin_menu(),
    )


@router.message(F.text == "➕ افزودن کانفیگ")
async def add_config_start_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(AdminConfigStates.waiting_for_category)
    await message.answer(
        "دسته‌بندی کانفیگ‌ها را ارسال کنید.\n"
        "مثال: `napsternetv` یا `v2ray`",
        parse_mode="Markdown",
        reply_markup=build_admin_menu(),
    )


@router.message(AdminConfigStates.waiting_for_category, F.text)
async def receive_category_handler(message: Message, state: FSMContext) -> None:
    category = message.text.strip()
    if not category:
        await message.answer("دسته‌بندی معتبر نیست. لطفاً دوباره ارسال کنید.")
        return

    await state.update_data(category=category)
    await state.set_state(AdminConfigStates.waiting_for_configs)
    await message.answer(
        "حالا متن یک کانفیگ یا لیستی از کانفیگ‌ها را بفرستید.\n"
        "هر کانفیگ را در یک خط جداگانه ارسال کنید.",
        reply_markup=build_admin_menu(),
    )


@router.message(AdminConfigStates.waiting_for_configs, F.text)
async def receive_configs_handler(
    message: Message,
    state: FSMContext,
    db: DatabaseHandler,
) -> None:
    state_data = await state.get_data()
    category = state_data.get("category")
    if not category:
        await state.clear()
        await message.answer("وضعیت ذخیره‌سازی نامعتبر شد. لطفاً دوباره تلاش کنید.")
        return

    configs = [line.strip() for line in message.text.splitlines() if line.strip()]
    if not configs:
        await message.answer("هیچ کانفیگ معتبری دریافت نشد. لطفاً دوباره ارسال کنید.")
        return

    try:
        for config in configs:
            await db.add_config(config, category)
    except Exception:
        logger.exception("Adding configs failed for category=%s", category)
        await message.answer("ذخیره کانفیگ‌ها با خطا مواجه شد. دوباره تلاش کنید.")
        return

    await state.clear()
    await message.answer(
        f"{len(configs)} کانفیگ در دسته‌بندی {category} ذخیره شد.",
        reply_markup=build_admin_menu(),
    )


@router.message(F.text == "📊 آمار موجودی")
async def stock_stats_handler(message: Message, db: DatabaseHandler) -> None:
    try:
        stock_counts = await db.get_stock_count()
    except Exception:
        logger.exception("Fetching stock count failed")
        await message.answer("دریافت آمار موجودی با خطا مواجه شد.")
        return

    if not stock_counts:
        await message.answer("در حال حاضر هیچ کانفیگ فروخته‌نشده‌ای ثبت نشده است.")
        return

    lines = ["📊 آمار کانفیگ‌های فروخته‌نشده:"]
    for category, count in stock_counts:
        lines.append(f"- {category}: {count}")

    await message.answer("\n".join(lines), reply_markup=build_admin_menu())


def build_amount_keyboard(user_id: int) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for amount in (50000, 100000, 200000):
        builder.add(
            InlineKeyboardButton(
                text=f"{amount:,} تومان".replace(",", "٬"),
                callback_data=f"receipt_amount:{user_id}:{amount}",
            )
        )
    builder.adjust(1)
    return builder


@router.callback_query(F.data.startswith("approve_receipt:"))
async def approve_receipt_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    user_id = int(callback.data.split(":")[1])
    await state.set_state(AdminRechargeStates.waiting_for_amount)
    await state.update_data(target_user_id=user_id)
    await callback.message.answer(
        "💳 مبلغ شارژ را انتخاب کنید یا عدد مبلغ را به تومان بفرستید.",
        reply_markup=build_amount_keyboard(user_id).as_markup(),
    )


@router.callback_query(F.data.startswith("receipt_amount:"))
async def quick_amount_handler(
    callback: CallbackQuery,
    state: FSMContext,
    db: DatabaseHandler,
    bot: Bot,
) -> None:
    await callback.answer()
    _, user_id_text, amount_text = callback.data.split(":")
    user_id = int(user_id_text)
    amount = int(amount_text)

    await apply_wallet_charge(
        message=callback.message,
        state=state,
        db=db,
        bot=bot,
        user_id=user_id,
        amount=amount,
    )


@router.message(AdminRechargeStates.waiting_for_amount, F.text)
async def manual_amount_handler(
    message: Message,
    state: FSMContext,
    db: DatabaseHandler,
    bot: Bot,
) -> None:
    cleaned_amount = message.text.replace("٬", "").replace(",", "").strip()
    if not cleaned_amount.isdigit():
        await message.answer("⚠️ مبلغ باید فقط عدد باشد. مثلاً `150000`", parse_mode="Markdown")
        return

    state_data = await state.get_data()
    user_id = state_data.get("target_user_id")
    if not user_id:
        await state.clear()
        await message.answer("⚠️ اطلاعات کاربر پیدا نشد. لطفاً دوباره از ابتدا اقدام کنید.")
        return

    await apply_wallet_charge(
        message=message,
        state=state,
        db=db,
        bot=bot,
        user_id=int(user_id),
        amount=int(cleaned_amount),
    )


async def apply_wallet_charge(
    message: Message,
    state: FSMContext,
    db: DatabaseHandler,
    bot: Bot,
    user_id: int,
    amount: int,
) -> None:
    if amount <= 0:
        await message.answer("⚠️ مبلغ باید بیشتر از صفر باشد.")
        return

    try:
        await db.update_balance(user_id, amount)
        new_balance = await db.get_user_balance(user_id)
        await bot.send_message(
            user_id,
            f"✅ فیش شما تایید شد و کیف پول‌تان به مبلغ {amount:,} تومان شارژ شد.\n"
            f"💰 موجودی فعلی: {new_balance:,} تومان".replace(",", "٬"),
        )
    except Exception:
        logger.exception("Approving receipt failed for user_id=%s amount=%s", user_id, amount)
        await message.answer("❌ شارژ کیف پول با خطا مواجه شد. دوباره تلاش کنید.")
        return

    await state.clear()
    await message.answer(
        f"✅ کیف پول کاربر `{user_id}` به مبلغ {amount:,} تومان شارژ شد.".replace(",", "٬"),
        parse_mode="Markdown",
        reply_markup=build_admin_menu(),
    )


@router.callback_query(F.data.startswith("reject_receipt:"))
async def reject_receipt_handler(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer()
    user_id = int(callback.data.split(":")[1])

    try:
        await bot.send_message(
            user_id,
            "❌ فیش شما مورد تایید نبود. لطفاً اطلاعات واریز را بررسی کرده و دوباره ارسال کنید.",
        )
    except Exception:
        logger.exception("Rejecting receipt notification failed for user_id=%s", user_id)
        await callback.message.answer("⚠️ فیش رد شد، اما ارسال پیام به کاربر ناموفق بود.")
        return

    await callback.message.answer("❌ فیش کاربر رد شد.", reply_markup=build_admin_menu())


@router.message(F.text == "🔙 بازگشت به منوی اصلی")
async def back_to_main_menu_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "به منوی اصلی برگشتید.",
        reply_markup=ReplyKeyboardRemove(),
    )
    await message.answer(
        "منوی اصلی:",
        reply_markup=build_start_menu(),
    )
