from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, KeyboardButton, Message, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from config import settings
from database.db_handler import DatabaseHandler
from keyboards.admin_menu import build_admin_menu
from keyboards.shop_menu import build_admin_category_price_menu
from keyboards.start_menu import build_start_menu
from utils.states import AdminPriceStates, AdminRechargeStates, AdminStates

logger = logging.getLogger(__name__)

router = Router(name="admin")
router.message.filter(F.from_user.id == settings.ADMIN_ID)
router.callback_query.filter(F.from_user.id == settings.ADMIN_ID)


def build_broadcast_preview_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تایید و ارسال", callback_data="confirm_broadcast"),
        InlineKeyboardButton(text="❌ لغو", callback_data="cancel_broadcast"),
    )
    return builder


def build_add_config_categories_keyboard(categories: list[tuple[int, str, int, int]]) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for category_id, name, _price, _stock_count in categories:
        builder.button(text=f"📁 {name}", callback_data=f"admin_add_config_category:{category_id}")
    builder.button(text="❌ انصراف", callback_data="cancel_add_config")
    builder.adjust(1)
    return builder


def build_cancel_reply_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="❌ انصراف از افزودن"))
    return builder.as_markup(resize_keyboard=True)


@router.message(Command("admin"))
async def admin_panel_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "پنل ادمین فعال شد. یکی از گزینه‌های زیر را انتخاب کنید.",
        reply_markup=build_admin_menu(),
    )


@router.message(F.text == "➕ افزودن کانفیگ جدید")
async def add_new_configs_start_handler(message: Message, state: FSMContext, db: DatabaseHandler) -> None:
    try:
        categories = await db.get_all_categories_with_details()
    except Exception:
        logger.exception("Fetching categories for add config failed")
        await message.answer("❌ دریافت دسته‌بندی‌ها با خطا مواجه شد.")
        return

    if not categories:
        await message.answer("⚠️ هیچ دسته‌بندی‌ای ثبت نشده است.")
        return

    await state.set_state(AdminStates.waiting_for_add_config_category)
    await message.answer(
        "➕ یک دسته‌بندی انتخاب کنید:",
        reply_markup=build_add_config_categories_keyboard(categories).as_markup(),
    )


@router.callback_query(
    AdminStates.waiting_for_add_config_category,
    F.data.startswith("admin_add_config_category:"),
)
async def add_new_configs_category_selected(
    callback: CallbackQuery,
    state: FSMContext,
    db: DatabaseHandler,
) -> None:
    await callback.answer()
    category_id = int(callback.data.split(":")[1])

    try:
        category = await db.get_category_details(category_id)
    except Exception:
        logger.exception("Loading category failed for category_id=%s", category_id)
        await callback.message.answer("❌ دریافت اطلاعات دسته‌بندی با خطا مواجه شد.")
        return

    if category is None:
        await state.clear()
        await callback.message.answer("⚠️ این دسته‌بندی دیگر در دسترس نیست.")
        return

    _, category_name, _price, _stock_count = category
    await state.update_data(add_config_category_name=category_name)
    await state.set_state(AdminStates.waiting_for_config_list)
    await callback.message.answer(
        f"دسته‌بندی انتخاب‌شده: {category_name}\n\n"
        "کانفیگ‌ها را ارسال کنید.\n"
        "هر خط، یک کانفیگ محسوب می‌شود.",
        reply_markup=build_cancel_reply_keyboard(),
    )


@router.message(AdminStates.waiting_for_config_list, F.text)
async def add_new_configs_receive_list(
    message: Message,
    state: FSMContext,
    db: DatabaseHandler,
) -> None:
    state_data = await state.get_data()
    category_name = state_data.get("add_config_category_name")
    if not category_name:
        await state.clear()
        await message.answer("⚠️ دسته‌بندی انتخاب نشده است. دوباره تلاش کنید.")
        return

    configs = [line.strip() for line in message.text.splitlines() if line.strip()]
    if not configs:
        await message.answer("⚠️ هیچ کانفیگ معتبری دریافت نشد. لطفاً دوباره ارسال کنید.")
        return

    try:
        inserted_count = await db.add_new_configs(category_name=category_name, configs=configs)
    except Exception:
        logger.exception("Adding new config list failed for category=%s", category_name)
        await message.answer("❌ ذخیره کانفیگ‌ها با خطا مواجه شد.")
        return

    await state.clear()
    await message.answer(
        f"✅ تعداد `{inserted_count}` کانفیگ جدید به دسته‌بندی `{category_name}` اضافه شد.",
        parse_mode="Markdown",
        reply_markup=build_admin_menu(),
    )


@router.callback_query(
    AdminStates.waiting_for_add_config_category,
    F.data == "cancel_add_config",
)
async def cancel_add_config_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.answer(
        "❌ عملیات افزودن کانفیگ لغو شد.",
        reply_markup=build_admin_menu(),
    )


@router.message(
    F.text == "❌ انصراف از افزودن",
    StateFilter(AdminStates.waiting_for_add_config_category, AdminStates.waiting_for_config_list),
)
async def cancel_add_config_message_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "❌ عملیات افزودن کانفیگ لغو شد.",
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


@router.message(F.text == "💰 مدیریت قیمت‌ها")
async def manage_prices_handler(message: Message, state: FSMContext, db: DatabaseHandler) -> None:
    try:
        categories = await db.get_all_categories_with_details()
    except Exception:
        logger.exception("Fetching categories for price management failed")
        await message.answer("❌ دریافت دسته‌بندی‌ها با خطا مواجه شد.")
        return

    if not categories:
        await message.answer("📦 هنوز هیچ دسته‌بندی‌ای در انبار ثبت نشده است.")
        return

    await state.set_state(AdminPriceStates.waiting_for_category_selection)
    await message.answer(
        "💰 برای تنظیم قیمت، یکی از دسته‌بندی‌های زیر را انتخاب کنید:",
        reply_markup=build_admin_category_price_menu(categories),
    )


@router.message(F.text == "📈 گزارش فروش")
async def sales_report_handler(message: Message, db: DatabaseHandler) -> None:
    try:
        stats = await db.get_admin_stats()
    except Exception:
        logger.exception("Fetching admin stats failed")
        await message.answer("❌ دریافت گزارش فروش با خطا مواجه شد.")
        return

    total_income = stats.get("total_sales_amount", 0)
    total_recharges = stats.get("total_recharges", 0)
    sales_today = stats.get("sales_today", 0)
    total_users = stats.get("total_users", 0)
    await message.answer(
        "📈 <b>گزارش مالی فروشگاه</b>\n\n"
        f"💵 <b>کل درآمد فروش:</b> {total_income:,} تومان\n"
        f"💳 <b>مجموع شارژهای تاییدشده:</b> {total_recharges:,} تومان\n"
        f"🛒 <b>تعداد فروش امروز (UTC):</b> {sales_today}\n"
        f"👥 <b>تعداد کل کاربران:</b> {total_users}".replace(",", "٬"),
        parse_mode="HTML",
        reply_markup=build_admin_menu(),
    )


@router.message(F.text == "📊 آمار کلی")
async def admin_overall_stats_handler(message: Message, db: DatabaseHandler) -> None:
    try:
        stats = await db.get_admin_stats()
    except Exception:
        logger.exception("Fetching overall admin stats failed")
        await message.answer("❌ دریافت آمار کلی با خطا مواجه شد.")
        return

    await message.answer(
        "<blockquote>\n\n"
        "📊 آمار کلی ربات\n\n"
        f"👥 تعداد کل کاربران: {stats.get('total_users', 0)} نفر\n\n"
        f"💰 مجموع فروش کل: {stats.get('total_sales_amount', 0):,} تومان\n\n"
        f"🛒 تعداد کل سفارشات: {stats.get('total_purchases', 0)} عدد\n\n"
        f"🔗 کل کاربران دعوتی (رفرال): {stats.get('total_referrals', 0)} نفر\n\n"
        "</blockquote>".replace(",", "٬"),
        parse_mode="HTML",
        reply_markup=build_admin_menu(),
    )


@router.callback_query(F.data == "admin_stats")
async def admin_overall_stats_callback_handler(callback: CallbackQuery, db: DatabaseHandler) -> None:
    await callback.answer()
    try:
        stats = await db.get_admin_stats()
    except Exception:
        logger.exception("Fetching overall admin stats by callback failed")
        await callback.message.answer("❌ دریافت آمار کلی با خطا مواجه شد.")
        return

    await callback.message.answer(
        "<blockquote>\n\n"
        "📊 آمار کلی ربات\n\n"
        f"👥 تعداد کل کاربران: {stats.get('total_users', 0)} نفر\n\n"
        f"💰 مجموع فروش کل: {stats.get('total_sales_amount', 0):,} تومان\n\n"
        f"🛒 تعداد کل سفارشات: {stats.get('total_purchases', 0)} عدد\n\n"
        f"🔗 کل کاربران دعوتی (رفرال): {stats.get('total_referrals', 0)} نفر\n\n"
        "</blockquote>".replace(",", "٬"),
        parse_mode="HTML",
        reply_markup=build_admin_menu(),
    )


@router.callback_query(
    AdminPriceStates.waiting_for_category_selection,
    F.data.startswith("admin_price_category:"),
)
async def select_price_category_handler(
    callback: CallbackQuery,
    state: FSMContext,
    db: DatabaseHandler,
) -> None:
    await callback.answer()
    category_id = int(callback.data.split(":")[1])

    try:
        category = await db.get_category_details(category_id)
    except Exception:
        logger.exception("Fetching selected category failed for category_id=%s", category_id)
        await callback.message.answer("❌ اطلاعات دسته‌بندی قابل دریافت نیست.")
        return

    if category is None:
        await state.clear()
        await callback.message.answer("⚠️ این دسته‌بندی دیگر در دسترس نیست.")
        return

    _, category_name, current_price, stock_count = category
    await state.set_state(AdminPriceStates.waiting_for_price)
    await state.update_data(price_category_name=category_name)
    await callback.message.answer(
        f"💳 دسته‌بندی: {category_name}\n"
        f"💰 قیمت فعلی: {current_price:,} تومان\n"
        f"📦 موجودی فعلی: {stock_count}\n\n"
        "عدد قیمت جدید را به تومان ارسال کنید.".replace(",", "٬"),
    )


@router.message(AdminPriceStates.waiting_for_price, F.text)
async def set_category_price_handler(
    message: Message,
    state: FSMContext,
    db: DatabaseHandler,
) -> None:
    cleaned_price = message.text.replace("٬", "").replace(",", "").strip()
    if not cleaned_price.isdigit():
        await message.answer("⚠️ قیمت باید فقط عدد باشد. مثلاً `50000`", parse_mode="Markdown")
        return

    state_data = await state.get_data()
    category_name = state_data.get("price_category_name")
    if not category_name:
        await state.clear()
        await message.answer("⚠️ دسته‌بندی انتخاب‌شده پیدا نشد. دوباره تلاش کنید.")
        return

    price = int(cleaned_price)

    try:
        await db.set_category_price(category_name, price)
    except Exception:
        logger.exception("Updating category price failed for category=%s", category_name)
        await message.answer("❌ ذخیره قیمت جدید با خطا مواجه شد.")
        return

    await state.clear()
    await message.answer(
        f"✅ قیمت دسته‌بندی {category_name} روی {price:,} تومان تنظیم شد.".replace(",", "٬"),
        reply_markup=build_admin_menu(),
    )


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
        await db.add_transaction(
            user_id=user_id,
            amount=amount,
            txn_type="recharge",
            description="admin approved recharge",
        )
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


@router.message(F.text == "📢 ارسال همگانی")
async def broadcast_start_handler(message: Message, state: FSMContext, db: DatabaseHandler) -> None:
    try:
        users_count = await db.get_all_users_count()
    except Exception:
        logger.exception("Loading users count failed")
        await message.answer("❌ دریافت تعداد کاربران با خطا مواجه شد.")
        return

    await state.set_state(AdminStates.waiting_for_broadcast_message)
    await message.answer(
        f"📢 ارسال همگانی فعال شد.\n"
        f"👥 تعداد کاربران: {users_count}\n\n"
        "پیام موردنظر را ارسال کنید (متن، عکس، ویدیو، فایل و ...).",
        reply_markup=build_admin_menu(),
    )


@router.message(AdminStates.waiting_for_broadcast_message)
async def broadcast_send_handler(
    message: Message,
    state: FSMContext,
) -> None:
    await state.update_data(
        broadcast_source_chat_id=message.chat.id,
        broadcast_source_message_id=message.message_id,
    )
    await message.answer("🔎 پیش‌نمایش پیام همگانی:")
    await message.copy_to(chat_id=message.chat.id)
    await message.answer(
        "آیا ارسال همگانی انجام شود؟",
        reply_markup=build_broadcast_preview_keyboard().as_markup(),
    )


@router.callback_query(F.data == "confirm_broadcast")
async def confirm_broadcast_handler(
    callback: CallbackQuery,
    state: FSMContext,
    db: DatabaseHandler,
    bot: Bot,
) -> None:
    await callback.answer()
    state_data = await state.get_data()
    source_chat_id = state_data.get("broadcast_source_chat_id")
    source_message_id = state_data.get("broadcast_source_message_id")

    if not source_chat_id or not source_message_id:
        await state.clear()
        await callback.message.answer("⚠️ پیام پیش‌نمایش پیدا نشد. دوباره ارسال همگانی را شروع کنید.")
        return

    try:
        user_ids = await db.get_all_user_ids()
    except Exception:
        logger.exception("Loading user ids failed")
        await callback.message.answer("❌ دریافت لیست کاربران با خطا مواجه شد.")
        return

    success_count = 0
    failed_count = 0

    for user_id in user_ids:
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=int(source_chat_id),
                message_id=int(source_message_id),
            )
            success_count += 1
        except Exception:
            failed_count += 1

    await state.clear()
    await callback.message.answer(
        "✅ ارسال همگانی تمام شد.\n"
        f"📬 ارسال موفق: {success_count}\n"
        f"❌ ارسال ناموفق: {failed_count}",
        reply_markup=build_admin_menu(),
    )


@router.callback_query(F.data == "cancel_broadcast")
async def cancel_broadcast_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.answer("❌ ارسال همگانی لغو شد.", reply_markup=build_admin_menu())


@router.message(F.text == "💳 تنظیم شماره کارت")
async def set_card_number_start_handler(message: Message, state: FSMContext, db: DatabaseHandler) -> None:
    current_card = await db.get_setting("admin_card_number", settings.ADMIN_CARD_NUMBER)
    await state.set_state(AdminStates.waiting_for_card_number)
    await message.answer(
        "💳 تنظیم شماره کارت\n"
        f"شماره کارت فعلی: `{current_card}`\n\n"
        "شماره کارت جدید را ارسال کنید.",
        parse_mode="Markdown",
        reply_markup=build_admin_menu(),
    )


@router.message(AdminStates.waiting_for_card_number, F.text)
async def set_card_number_handler(message: Message, state: FSMContext, db: DatabaseHandler) -> None:
    card_number = message.text.strip().replace(" ", "").replace("-", "")
    if not card_number.isdigit() or len(card_number) != 16:
        await message.answer(
            "⚠️ شماره کارت نامعتبر است.\n"
            "لطفاً شماره کارت را فقط به‌صورت ۱۶ رقم عددی ارسال کنید.\n"
            "نمونه: `6037997900000000`",
            parse_mode="Markdown",
        )
        return

    try:
        await db.set_setting("admin_card_number", card_number)
    except Exception:
        logger.exception("Updating admin card number failed")
        await message.answer("❌ ذخیره شماره کارت با خطا مواجه شد.")
        return

    await state.clear()
    await message.answer(
        f"✅ شماره کارت جدید ذخیره شد:\n`{card_number}`",
        parse_mode="Markdown",
        reply_markup=build_admin_menu(),
    )


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
