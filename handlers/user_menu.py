from __future__ import annotations

import html
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import settings
from database.db_handler import DatabaseHandler
from keyboards.shop_menu import (
    build_categories_buy_menu,
    build_purchase_confirmation_menu,
    build_recharge_prompt_menu,
)
from keyboards.purchases_menu import build_user_purchases_keyboard
from utils.states import RechargeStates

logger = logging.getLogger(__name__)

router = Router(name="user_menu")

PROFILE_MESSAGE = """
<tg-emoji emoji-id='5190458330719461749'>🧑‍💻</tg-emoji>
<b>پنل کاربری شما</b>

<tg-emoji emoji-id='5809707982472090166'>🆔</tg-emoji> • شناسه عددی: {user_id}

<tg-emoji emoji-id='5373052667671093676'>🛍</tg-emoji> • تعداد کل خریدها: {purchases_count}

<tg-emoji emoji-id='5958399943533138158'>💰</tg-emoji> • موجودی کیف پول: {balance} تومان
""".strip()


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


@router.callback_query(F.data == "connection_guide")
async def connection_guide_handler(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        "<blockquote>"
        "<b>📚 راهنمای اتصال به سرویس‌ها</b>\n\n"
        "برای استفاده از سرویس‌های خریداری شده، ابتدا نرم‌افزار متناسب با دستگاه خود را نصب کنید:\n\n"
        "<b>📱 اندروید:</b>\n"
        "<a href=\"https://play.google.com/store/apps/details?id=com.v2ray.ang\">V2rayNG</a> (پیشنهادی)\n"
        "<b>🍎 آیفون (iOS):</b>\n"
        "<a href=\"https://apps.apple.com/us/app/v2box-v2ray-client/id1641830530\">V2Box</a>\n"
        "<a href=\"https://apps.apple.com/us/app/streisand/id6450534064\">Streisand</a>\n"
        "<b>💻 ویندوز:</b>\n"
        "<a href=\"https://github.com/2dust/v2rayN/releases\">V2rayN</a>\n"
        "<b>📖 آموزش کوتاه:</b>\n\n"
        "۱. لینک کانفیگ را از بخش «سرویس‌های من» کپی کنید.\n\n"
        "۲. وارد برنامه شده و علامت + یا Import را بزنید.\n\n"
        "۳. گزینه Import from Clipboard را انتخاب کرده و متصل شوید."
        "</blockquote>",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


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
        purchases_count = await db.get_user_purchases_count(user_id)
    except Exception:
        logger.exception("Fetching user profile failed for user_id=%s", user_id)
        await callback.message.answer("❌ دریافت اطلاعات پروفایل با خطا مواجه شد.")
        return

    profile_builder = InlineKeyboardBuilder()
    profile_builder.button(
        text="📜 تاریخچه خریدهای اخیر",
        callback_data="recent_purchase_history",
    )
    profile_builder.adjust(1)

    await callback.message.answer(
        text=PROFILE_MESSAGE.format(
            user_id=user_id,
            purchases_count=purchases_count,
            balance=f"{balance:,}".replace(",", "٬"),
        ),
        parse_mode="HTML",
        reply_markup=profile_builder.as_markup(),
    )


@router.callback_query(F.data == "referral_info")
async def referral_info_handler(callback: CallbackQuery, db: DatabaseHandler, bot: Bot) -> None:
    await callback.answer()
    if callback.from_user is None:
        return

    user_id = callback.from_user.id
    try:
        referral_count = await db.get_referral_count(user_id)
        bot_info = await bot.get_me()
    except Exception:
        logger.exception("Loading referral info failed for user_id=%s", user_id)
        await callback.message.answer("❌ دریافت اطلاعات زیرمجموعه‌گیری با خطا مواجه شد.")
        return

    bot_username = bot_info.username or ""
    referral_link = f"https://t.me/{bot_username}?start={user_id}" if bot_username else f"/start {user_id}"
    await callback.message.answer(
        "👥 سیستم زیرمجموعه‌گیری\n\n"
        f"🔗 لینک اختصاصی شما:\n<code>{html.escape(referral_link)}</code>\n\n"
        f"📊 تعداد کل افراد دعوت‌شده: <b>{referral_count}</b>\n\n"
        "🎁 با دعوت هر نفر از دوستانتان، مبلغ ۲,۰۰۰ تومان اعتبار هدیه دریافت کنید!",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "recent_purchase_history")
async def recent_purchase_history_handler(
    callback: CallbackQuery,
    db: DatabaseHandler,
) -> None:
    await callback.answer()
    if callback.from_user is None:
        return

    user_id = callback.from_user.id
    try:
        history = await db.get_user_purchase_history(user_id=user_id, limit=5)
    except Exception:
        logger.exception("Fetching purchase history failed for user_id=%s", user_id)
        await callback.message.answer("❌ دریافت تاریخچه خرید با خطا مواجه شد.")
        return

    if not history:
        await callback.message.answer("هنوز خریدی ثبت نکرده‌اید")
        return

    lines = ["📜 ۵ خرید اخیر شما:"]
    for location_name, config_text in history:
        safe_location = html.escape(location_name or "نامشخص")
        safe_config = html.escape(config_text or "")
        lines.append("━━━━━━━━━━━━━━")
        lines.append(f"📍 لوکیشن: {safe_location}")
        lines.append(f"<code>{safe_config}</code>")

    back_builder = InlineKeyboardBuilder()
    back_builder.button(text="🔙 بازگشت به پروفایل", callback_data="user_profile")
    back_builder.adjust(1)

    await callback.message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=back_builder.as_markup(),
    )


@router.callback_query(F.data.in_({"recharge_wallet", "recharge"}))
async def recharge_wallet_handler(
    callback: CallbackQuery,
    state: FSMContext,
    db: DatabaseHandler,
) -> None:
    await callback.answer()
    await state.set_state(RechargeStates.waiting_for_receipt)
    card_number = await db.get_setting("admin_card_number", settings.ADMIN_CARD_NUMBER)
    await callback.message.answer(
        "💳 برای شارژ حساب، مبلغ را به شماره کارت زیر واریز کنید:\n"
        f"`{card_number}`\n\n"
        "📸 سپس عکس فیش واریزی را همین‌جا ارسال کنید.",
        parse_mode="Markdown",
    )


@router.callback_query(F.data == "buy_service")
async def buy_service_handler(callback: CallbackQuery, db: DatabaseHandler) -> None:
    await callback.answer()

    try:
        all_categories = await db.get_all_categories_with_details()
    except Exception:
        logger.exception("Fetching buyable categories failed")
        await callback.message.answer("❌ دریافت لیست سرویس‌ها با خطا مواجه شد.")
        return

    categories = [category for category in all_categories if category[3] > 0]
    if not categories:
        await callback.message.answer("📦 در حال حاضر هیچ سرویسی برای فروش موجود نیست.")
        return

    await callback.message.answer(
        "🛍 سرویس مورد نظر را انتخاب کنید:",
        reply_markup=build_categories_buy_menu(categories),
    )


@router.callback_query(F.data.startswith("buy_category:"))
async def select_category_for_purchase(
    callback: CallbackQuery,
    db: DatabaseHandler,
) -> None:
    await callback.answer()
    if callback.from_user is None:
        return

    category_id = int(callback.data.split(":")[1])

    try:
        category = await db.get_category_details(category_id)
        balance = await db.get_user_balance(callback.from_user.id)
    except Exception:
        logger.exception("Preparing purchase confirmation failed for category_id=%s", category_id)
        await callback.message.answer("❌ آماده‌سازی خرید با خطا مواجه شد.")
        return

    if category is None or category[3] <= 0:
        await callback.message.answer("⚠️ این سرویس دیگر موجود نیست.")
        return

    _, category_name, price, stock_count = category
    await callback.message.answer(
        f"🛍 محصول انتخابی: {category_name}\n"
        f"💰 قیمت: {price:,} تومان\n"
        f"💳 موجودی کیف پول شما: {balance:,} تومان\n"
        f"📦 موجودی انبار: {stock_count}\n\n"
        "در صورت تایید، روی دکمه زیر بزنید.".replace(",", "٬"),
        reply_markup=build_purchase_confirmation_menu(category_id),
    )


@router.callback_query(F.data.startswith("confirm_purchase:"))
async def confirm_purchase_handler(
    callback: CallbackQuery,
    db: DatabaseHandler,
    bot: Bot,
) -> None:
    await callback.answer()
    if callback.from_user is None:
        return

    user_id = callback.from_user.id
    category_id = int(callback.data.split(":")[1])

    try:
        category = await db.get_category_details(category_id)
        balance = await db.get_user_balance(user_id)
    except Exception:
        logger.exception("Loading purchase data failed for user_id=%s category_id=%s", user_id, category_id)
        await callback.message.answer("❌ بررسی اطلاعات خرید با خطا مواجه شد.")
        return

    if category is None:
        await callback.message.answer("⚠️ این دسته‌بندی دیگر در دسترس نیست.")
        return

    _, category_name, price, _ = category
    if balance < price:
        await callback.message.answer(
            f"❌ موجودی کیف پول شما کافی نیست.\n"
            f"💰 قیمت سرویس: {price:,} تومان\n"
            f"💳 موجودی فعلی: {balance:,} تومان".replace(",", "٬"),
            reply_markup=build_recharge_prompt_menu(),
        )
        return

    try:
        available_config = await db.get_available_config(category_name)
    except Exception:
        logger.exception("Fetching available config failed for category=%s", category_name)
        await callback.message.answer("❌ دریافت کانفیگ با خطا مواجه شد.")
        return

    if available_config is None:
        await callback.message.answer("⚠️ متاسفانه موجودی این سرویس تمام شده است.")
        return

    config_id, config_content = available_config

    try:
        purchase_completed = await db.complete_purchase(user_id, config_id, price)
    except Exception:
        logger.exception("Completing purchase failed for user_id=%s config_id=%s", user_id, config_id)
        await callback.message.answer("❌ انجام خرید با خطا مواجه شد. دوباره تلاش کنید.")
        return

    if not purchase_completed:
        await callback.message.answer(
            "⚠️ خرید انجام نشد؛ ممکن است موجودی کیف پول یا انبار تغییر کرده باشد. دوباره تلاش کنید."
        )
        return

    try:
        new_balance = await db.get_user_balance(user_id)
        await callback.message.answer(
            f"✅ خرید شما با موفقیت انجام شد.\n"
            f"🛍 سرویس: {category_name}\n"
            f"💰 مبلغ کسرشده: {price:,} تومان\n"
            f"💳 موجودی جدید: {new_balance:,} تومان\n\n"
            "📡 کانفیگ شما در پیام بعدی ارسال می‌شود.".replace(",", "٬"),
        )
        await callback.message.answer(config_content)
        await bot.send_message(
            settings.ADMIN_ID,
            f"🧾 فروش جدید انجام شد\n"
            f"👤 کاربر: `{user_id}`\n"
            f"🛍 دسته‌بندی: {category_name}\n"
            f"💰 مبلغ: {price:,} تومان\n"
            f"🆔 شناسه کانفیگ: `{config_id}`".replace(",", "٬"),
            parse_mode="Markdown",
        )
    except Exception:
        logger.exception("Sending purchase result failed for user_id=%s config_id=%s", user_id, config_id)
        await callback.message.answer("⚠️ خرید انجام شد، اما ارسال نتیجه با خطا مواجه شد.")


@router.callback_query(F.data == "cancel_purchase_flow")
async def cancel_purchase_flow_handler(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer("❌ فرآیند خرید لغو شد.")


@router.callback_query(F.data == "my_services")
async def my_services_handler(callback: CallbackQuery, db: DatabaseHandler) -> None:
    await callback.answer()
    if callback.from_user is None:
        return

    user_id = callback.from_user.id
    try:
        purchases = await db.get_user_purchases(user_id)
    except Exception:
        logger.exception("Fetching user purchases failed for user_id=%s", user_id)
        await callback.message.answer("❌ دریافت سرویس‌های شما با خطا مواجه شد.")
        return

    if not purchases:
        await callback.message.answer("📂 هنوز سرویسی خریداری نکرده‌اید.")
        return

    latest_purchases = purchases[:15]
    await callback.message.answer(
        "📂 سرویس‌های خریداری‌شده شما:\n"
        "برای مشاهده جزئیات هر سرویس، روی دکمه همان خرید بزنید.",
        reply_markup=build_user_purchases_keyboard(latest_purchases),
    )


@router.callback_query(F.data.startswith("purchase_info:"))
async def purchase_info_handler(callback: CallbackQuery, db: DatabaseHandler) -> None:
    await callback.answer()
    if callback.from_user is None:
        return

    config_id = int(callback.data.split(":")[1])

    try:
        purchases = await db.get_user_purchases(callback.from_user.id)
    except Exception:
        logger.exception("Loading purchase details failed for config_id=%s", config_id)
        await callback.message.answer("❌ دریافت جزئیات خرید با خطا مواجه شد.")
        return

    purchase = next((item for item in purchases if item[0] == config_id), None)
    if purchase is None:
        await callback.message.answer("⚠️ این خرید یافت نشد یا متعلق به شما نیست.")
        return

    _, category, config_content, sold_at = purchase
    shown_time = sold_at.replace("T", " ")[:19] if sold_at else "N/A"
    await callback.message.answer(
        f"🛍 سرویس: {category}\n"
        f"🕒 زمان خرید (UTC): {shown_time}\n"
        f"🆔 کد کانفیگ: `{config_id}`\n\n"
        f"{config_content}",
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


@router.callback_query(F.data == "support")
async def support_handler(callback: CallbackQuery) -> None:
    await callback.answer()
    support_id = settings.SUPPORT_ID.strip()

    builder = InlineKeyboardBuilder()
    has_url_button = False
    if support_id.startswith("@") and len(support_id) > 1:
        username = support_id[1:]
        builder.button(text="🔗 ارتباط با پشتیبان", url=f"https://t.me/{username}")
        has_url_button = True
    elif support_id.startswith("https://t.me/"):
        builder.button(text="🔗 ارتباط با پشتیبان", url=support_id)
        has_url_button = True

    text = (
        "👨‍💻 پشتیبانی\n"
        f"برای ارتباط با پشتیبانی به این شناسه پیام دهید:\n<code>{support_id}</code>"
    )
    await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=builder.as_markup() if has_url_button else None,
    )
