from __future__ import annotations

import html
import logging
import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import settings
from database.db_handler import DatabaseHandler
from keyboards.user_menu import build_main_menu
from keyboards.user_menu import build_recharge_method_menu
from handlers.start import handle_start_entry
from keyboards.shop_menu import (
    build_model_configs_menu,
    build_insufficient_balance_menu,
    build_model_purchase_confirmation_menu,
    build_model_selection_menu,
    build_categories_buy_menu,
    build_purchase_confirmation_menu,
    build_recharge_prompt_menu,
)
from utils.states import RechargeStates
from utils.security import parse_int_callback_payload, rate_limiter

logger = logging.getLogger(__name__)

router = Router(name="user_menu")
MIN_RECHARGE_AMOUNT = 10_000
TELEGRAM_MAX_MESSAGE_LENGTH = 4096

PROFILE_MESSAGE = """
<tg-emoji emoji-id='5190458330719461749'>🧑‍💻</tg-emoji>
<b>پنل کاربری شما</b>

<tg-emoji emoji-id='5809707982472090166'>🆔</tg-emoji> • شناسه عددی: {user_id}

<tg-emoji emoji-id='5373052667671093676'>🛍</tg-emoji> • تعداد کل خریدها: {purchases_count}

<tg-emoji emoji-id='5958399943533138158'>💰</tg-emoji> • موجودی کیف پول: {balance} تومان
""".strip()


def format_toman(amount: int) -> str:
    return f"{amount:,}".replace(",", "٬")


def _normalize_service_text(value: object) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    return html.escape(text)


def _chunk_message(text: str, limit: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit + 1)
        if split_at <= 0:
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].lstrip("\n")

    if remaining:
        chunks.append(remaining.strip())
    return chunks


def build_my_services_actions_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    recharge_payload = {
        "text": "تمدید / شارژ",
        "callback_data": "recharge_wallet",
        "icon_custom_emoji_id": "5443127283898405358",
    }
    back_payload = {
        "text": "🔙 بازگشت به منوی اصلی",
        "callback_data": "main_menu",
        "icon_custom_emoji_id": "5372926953978341366",
    }
    try:
        recharge_button = InlineKeyboardButton(**recharge_payload)
    except TypeError:
        recharge_button = InlineKeyboardButton(
            text=recharge_payload["text"],
            callback_data=recharge_payload["callback_data"],
        )
    try:
        back_button = InlineKeyboardButton(**back_payload)
    except TypeError:
        back_button = InlineKeyboardButton(
            text=back_payload["text"],
            callback_data=back_payload["callback_data"],
        )
    builder.row(recharge_button, back_button)
    return builder.as_markup()


def build_receipt_review_keyboard(request_id: int) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    back_payload = "status=pending:page=1:uid=:uname="
    builder.row(
        InlineKeyboardButton(
            text="تایید ✅",
            callback_data=f"recharge_admin_approve:{request_id}:{back_payload}",
        ),
        InlineKeyboardButton(
            text="رد ❌",
            callback_data=f"recharge_admin_reject:{request_id}:{back_payload}",
        ),
    )
    return builder


@router.callback_query(F.data == "connection_guide")
async def connection_guide_handler(callback: CallbackQuery) -> None:
    await callback.answer()
    guide_text = (
        "📚• <b>راهنمای اتصال به سرویس‌ها</b>\n\n"
        "برای استفاده از سرویس‌های خریداری شده، ابتدا نرم‌افزار متناسب با دستگاه خود را نصب کنید:\n\n"
        "<tg-emoji emoji-id='5440910041391573452'>💚</tg-emoji> • <b>اندروید:</b>\n"
        "<tg-emoji emoji-id='6050646916109179497'>🔐</tg-emoji>• V2rayNG\n"
        "<tg-emoji emoji-id='6023639019290630537'>📱</tg-emoji>• Hiddify (پیشنهادی)\n"
        "<tg-emoji emoji-id='6050626661043411760'>🔐</tg-emoji>• Npv\n\n"
        "<tg-emoji emoji-id='5935790552787193983'>🍏</tg-emoji> <b>آیفون (iOS):</b>\n"
        "<tg-emoji emoji-id='5866266486942733691'>🔐</tg-emoji>• V2Box\n"
        "<tg-emoji emoji-id='5933950773481181919'>🔐</tg-emoji>• Streisand (پیشنهادی)\n\n"
        "<tg-emoji emoji-id='5933550168996581523'>💻</tg-emoji> <b>ویندوز:</b>\n"
        "<tg-emoji emoji-id='5866022060353918430'>📱</tg-emoji>• V2rayN\n\n"
        "<tg-emoji emoji-id='5874978802332865390'>😀</tg-emoji> <b>آموزش کوتاه:</b>\n\n"
        "۱. لینک کانفیگ را از بخش «سرویس‌های من» کپی کنید.\n\n"
        "۲. وارد برنامه شده و علامت + یا Import را بزنید.\n\n"
        "۳. گزینه Import from Clipboard را انتخاب کرده و متصل شوید."
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 بازگشت به منوی اصلی", callback_data="main_menu")

    await callback.message.edit_text(
        text=guide_text,
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "main_menu")
async def main_menu_handler(callback: CallbackQuery, state: FSMContext, db: DatabaseHandler, bot: Bot) -> None:
    await state.clear()
    await callback.answer()
    await handle_start_entry(callback.message, db, bot, start_text="/start")


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


@router.callback_query(F.data == "referral_menu")
async def referral_menu_handler(callback: CallbackQuery, db: DatabaseHandler, bot: Bot) -> None:
    await callback.answer()
    if callback.from_user is None:
        return

    user_id = callback.from_user.id
    try:
        referral_count = await db.get_referral_count(user_id)
        reward_raw = await db.get_setting("referral_reward_amount", "2000")
        reward_amount = int(str(reward_raw or "2000"))
        bot_info = await bot.get_me()
    except Exception:
        logger.exception("Loading referral info failed for user_id=%s", user_id)
        await callback.message.answer("❌ دریافت اطلاعات زیرمجموعه‌گیری با خطا مواجه شد.")
        return

    bot_username = (bot_info.username or "").strip()
    referral_link = f"https://t.me/{bot_username}?start={user_id}" if bot_username else f"/start {user_id}"
    await callback.message.answer(
        "<tg-emoji emoji-id='5372926953978341366'>👥</tg-emoji> • سیستم زیرمجموعه‌گیری\n\n"
        "<tg-emoji emoji-id='6221940219147459142'>🔗</tg-emoji> • لینک اختصاصی شما:\n"
        f"<code>{html.escape(referral_link)}</code>\n\n"
        f"<tg-emoji emoji-id='5231200819986047254'>📊</tg-emoji> • تعداد کل افراد دعوت‌شده: {referral_count}\n\n"
        "<tg-emoji emoji-id='6224341518182784992'>🎁</tg-emoji> • "
        f"با دعوت هر نفر از دوستانتان، مبلغ {format_toman(reward_amount)} تومان اعتبار هدیه دریافت کنید!",
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
    back_button_payload = {
        "text": "🔙 حساب کاربری",
        "callback_data": "user_profile",
        "icon_custom_emoji_id": "5372926953978341366",
    }
    try:
        back_button = InlineKeyboardButton(**back_button_payload)
    except TypeError:
        back_button = InlineKeyboardButton(
            text=back_button_payload["text"],
            callback_data=back_button_payload["callback_data"],
        )
    back_builder.row(back_button)
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
) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.answer(
        "💎 روش پرداخت خود رو انتخاب کنید",
        reply_markup=build_recharge_method_menu(),
    )


async def _start_card_recharge_flow(message: Message, state: FSMContext) -> None:
    await state.set_state(RechargeStates.waiting_amount)
    await message.answer(
        "<tg-emoji emoji-id=\"5445353829304387411\">💳</tg-emoji> شارژ کیف پول\n\n"
        "لطفاً مبلغ مورد نظر خود را به تومان وارد کنید.\n\n"
        "مثال:\n"
        "50000\n"
        "100000\n"
        "250000",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "recharge_method_card")
async def recharge_method_card_handler(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    await callback.answer()
    await _start_card_recharge_flow(callback.message, state)


def _sanitize_crypto_proof_text(value: str) -> str:
    clean = re.sub(r"\s+", " ", value or "").strip()
    return clean[:250]


@router.callback_query(F.data == "recharge_method_crypto")
async def recharge_method_crypto_handler(callback: CallbackQuery, state: FSMContext, db: DatabaseHandler) -> None:
    await callback.answer()
    await state.set_state(RechargeStates.waiting_for_crypto_proof)
    wallet_usdt_bep20 = await db.get_setting("crypto_usdt_bep20", "تنظیم نشده")
    wallet_tron_trc20 = await db.get_setting("crypto_tron_trc20", "تنظیم نشده")
    wallet_ton = await db.get_setting("crypto_ton", "تنظیم نشده")
    await callback.message.answer(
        "<tg-emoji emoji-id='5255887969880912405'>💚</tg-emoji> • ولتر تتر ( Bep20 )\n\n"
        f"<code>{html.escape(str(wallet_usdt_bep20))}</code>\n\n"
        "<tg-emoji emoji-id='5467463745418573549'>❤️</tg-emoji> • ولت ترون ( Trc20 )\n\n"
        f"<code>{html.escape(str(wallet_tron_trc20))}</code>\n\n"
        "<tg-emoji emoji-id='5256144821810115779'>💙</tg-emoji> • ولت تون ( Ton )\n\n"
        f"<code>{html.escape(str(wallet_ton))}</code>\n\n"
        "<tg-emoji emoji-id='5274099962655816924'>❗️</tg-emoji> • پس از تکمیل تراکنش ( اسکرین شات و هش ) را همینجا ارسال نمایید .\n\n"
        "<tg-emoji emoji-id='5420323339723881652'>⚠️</tg-emoji> • در صورت عدم ارسال هش یا اسکرین شات ، تراکنش شما تایید نخواهد شد",
        parse_mode="HTML",
    )


@router.message(RechargeStates.waiting_amount, F.text)
async def recharge_amount_handler(message: Message, state: FSMContext, db: DatabaseHandler) -> None:
    if message.from_user is None:
        return
    if not rate_limiter.allow(f"recharge_amount:{message.from_user.id}", 2.0):
        await message.answer("⚠️ درخواست‌ها خیلی سریع ارسال شدند. لطفاً کمی بعد دوباره تلاش کنید.")
        return

    raw_amount = message.text.replace("٬", "").replace(",", "").strip()
    if not raw_amount.isdigit():
        await message.answer("⚠️ لطفاً مبلغ را فقط به‌صورت عددی وارد کنید. مثال: `50000`", parse_mode="Markdown")
        return

    amount = int(raw_amount)
    if amount < MIN_RECHARGE_AMOUNT:
        await message.answer(
            f"⚠️ حداقل مبلغ شارژ {format_toman(MIN_RECHARGE_AMOUNT)} تومان است."
        )
        return

    card_number, card_holder_name = await db.get_payment_settings()
    if not card_number:
        card_number = settings.ADMIN_CARD_NUMBER

    holder_line = (
        f"<tg-emoji emoji-id='5278611606756942667'>👤</tg-emoji> • نام صاحب کارت: {html.escape(card_holder_name)}\n\n"
        if card_holder_name
        else ""
    )

    await state.update_data(recharge_amount=amount)
    await state.set_state(RechargeStates.waiting_for_receipt)
    await message.answer(
        f"<tg-emoji emoji-id='5445353829304387411'>💳</tg-emoji> • برای شارژ حساب، مبلغ {amount} تومان را به شماره کارت زیر واریز کنید:\n\n"
        f"<code>{html.escape(card_number)}</code>\n\n"
        f"{holder_line}"
        "<tg-emoji emoji-id='5431515281467917094'>🎥</tg-emoji> • سپس عکس فیش واریزی را همین‌جا ارسال کنید.",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "buy_service")
async def buy_service_handler(callback: CallbackQuery, db: DatabaseHandler) -> None:
    await callback.answer()
    if callback.from_user and not rate_limiter.allow(f"buy_service:{callback.from_user.id}", 1.0):
        await callback.message.answer("⚠️ درخواست‌ها خیلی سریع ارسال شدند. لطفاً کمی بعد دوباره تلاش کنید.")
        return
    await callback.message.answer(
        "⬇️• یکی از مدل های زیر را انتخاب کنید",
        reply_markup=build_model_selection_menu(),
    )


@router.callback_query(F.data.startswith("buy_model:"))
async def buy_model_handler(callback: CallbackQuery, db: DatabaseHandler) -> None:
    await callback.answer()
    data_parts = callback.data.split(":")
    if len(data_parts) != 2:
        await callback.message.answer("⚠️ درخواست نامعتبر است.")
        return
    model = data_parts[1]
    await send_model_configs_page(callback.message, db, model=model, page=1)


@router.callback_query(F.data.startswith("buy_model_page:"))
async def buy_model_page_handler(callback: CallbackQuery, db: DatabaseHandler) -> None:
    await callback.answer()
    data_parts = callback.data.split(":")
    if len(data_parts) != 3:
        await callback.message.answer("⚠️ درخواست نامعتبر است.")
        return
    model = data_parts[1]
    if not data_parts[2].isdigit():
        await callback.message.answer("⚠️ شماره صفحه نامعتبر است.")
        return
    page = max(1, int(data_parts[2]))
    await send_model_configs_page(callback.message, db, model=model, page=page)


async def send_model_configs_page(message: Message, db: DatabaseHandler, model: str, page: int) -> None:
    if model not in {"nox_plus", "nox_multi"}:
        await message.answer("⚠️ مدل انتخابی معتبر نیست.")
        return

    page_size = 6
    try:
        total_configs = await db.count_active_configs_by_model(model)
    except Exception:
        logger.exception("Counting model configs failed for model=%s", model)
        await message.answer("❌ دریافت لیست سرویس‌ها با خطا مواجه شد.")
        return

    if total_configs <= 0:
        await message.answer("📦 در حال حاضر سرویسی برای این مدل موجود نیست.")
        return

    total_pages = (total_configs + page_size - 1) // page_size
    safe_page = min(page, total_pages)
    offset = (safe_page - 1) * page_size

    try:
        configs = await db.get_active_configs_by_model(model=model, limit=page_size, offset=offset)
    except Exception:
        logger.exception("Loading model configs failed for model=%s page=%s", model, safe_page)
        await message.answer("❌ دریافت لیست کانفیگ‌ها با خطا مواجه شد.")
        return

    if model == "nox_plus":
        text = (
            '<tg-emoji emoji-id="5875306327948923856">💎</tg-emoji> • <b>سرویس : Nox Plus</b>\n\n'
            '<tg-emoji emoji-id="5802888128456823766">✅</tg-emoji> • حجم دلخواه خود را انتخاب کنید.'
        )
    else:
        text = (
            '<tg-emoji emoji-id="5920303364574285697">🍽</tg-emoji> • <b>سرویس : Nox Multi</b>\n\n'
            '<tg-emoji emoji-id="5802888128456823766">✅</tg-emoji> • حجم دلخواه خود را انتخاب کنید.'
        )

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=build_model_configs_menu(
            model=model,
            configs=configs,
            page=safe_page,
            total_pages=total_pages,
        ),
    )


@router.callback_query(F.data.startswith("buy_config:"))
async def buy_config_handler(callback: CallbackQuery, db: DatabaseHandler) -> None:
    await callback.answer()
    config_id = parse_int_callback_payload(callback.data, "buy_config:")
    if config_id is None:
        await callback.message.answer("⚠️ درخواست نامعتبر است.")
        return
    try:
        config = await db.get_model_config_details(config_id)
    except Exception:
        logger.exception("Loading config details failed for config_id=%s", config_id)
        await callback.message.answer("❌ دریافت جزئیات کانفیگ با خطا مواجه شد.")
        return

    if config is None:
        await callback.message.answer("⚠️ این کانفیگ دیگر موجود نیست.")
        return

    _, title, price, duration, description, _config_content = config
    await callback.message.answer(
        "📦 مشخصات سرویس\n\n"
        f"عنوان: {title}\n\n"
        f"قیمت: {price:,} تومان\n\n"
        f"موجودی: {duration}\n\n"
        "توضیحات:\n"
        f"{description}\n\n"
        "آیا مایل به خرید این سرویس هستید؟".replace(",", "٬"),
        reply_markup=build_model_purchase_confirmation_menu(config_id),
    )


@router.callback_query(F.data.startswith("buy_category:"))
async def select_category_for_purchase(
    callback: CallbackQuery,
    db: DatabaseHandler,
) -> None:
    await callback.answer()
    if callback.from_user is None:
        return

    category_id = parse_int_callback_payload(callback.data, "buy_category:")
    if category_id is None:
        await callback.message.answer("⚠️ درخواست نامعتبر است.")
        return

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
    if not rate_limiter.allow(f"confirm_purchase:{user_id}", 1.5):
        await callback.message.answer("⚠️ درخواست‌ها خیلی سریع ارسال شدند. لطفاً کمی بعد دوباره تلاش کنید.")
        return

    data_parts = callback.data.split(":")
    if len(data_parts) != 2:
        await callback.message.answer("⚠️ درخواست خرید نامعتبر است.")
        return
    payload = data_parts[1]
    if not payload.isdigit():
        await callback.message.answer("⚠️ درخواست خرید نامعتبر است.")
        return
    target_id = int(payload)

    try:
        category = await db.get_category_details(target_id)
        config_snapshot = await db.get_model_config_purchase_snapshot(target_id)
        balance = await db.get_user_balance(user_id)
    except Exception:
        logger.exception("Loading purchase data failed for user_id=%s category_id=%s", user_id, target_id)
        await callback.message.answer("❌ بررسی اطلاعات خرید با خطا مواجه شد.")
        return

    if category is None and config_snapshot is not None:
        logger.warning(
            "Rejected mixed purchase flow for user_id=%s target_id=%s (config id used in category flow)",
            user_id,
            target_id,
        )
        await callback.message.answer("⚠️ درخواست خرید نامعتبر است.")
        return

    if category is None:
        await callback.message.answer("⚠️ این دسته‌بندی دیگر در دسترس نیست.")
        return

    _, category_name, price, _ = category
    config_id, config_content, purchase_completed = await _complete_category_purchase(
        callback=callback,
        db=db,
        user_id=user_id,
        category_name=category_name,
        price=price,
        balance=balance,
    )
    if not purchase_completed:
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


async def _complete_category_purchase(
    callback: CallbackQuery,
    db: DatabaseHandler,
    *,
    user_id: int,
    category_name: str,
    price: int,
    balance: int,
) -> tuple[int | None, str | None, bool]:
    if balance < price:
        await callback.message.answer(
            f"❌ موجودی کیف پول شما کافی نیست.\n"
            f"💰 قیمت سرویس: {price:,} تومان\n"
            f"💳 موجودی فعلی: {balance:,} تومان".replace(",", "٬"),
            reply_markup=build_recharge_prompt_menu(),
        )
        return None, None, False

    try:
        available_config = await db.get_available_config(category_name)
    except Exception:
        logger.exception("Fetching available config failed for category=%s", category_name)
        await callback.message.answer("❌ دریافت کانفیگ با خطا مواجه شد.")
        return None, None, False

    if available_config is None:
        await callback.message.answer("⚠️ متاسفانه موجودی این سرویس تمام شده است.")
        return None, None, False

    config_id, config_content = available_config
    try:
        purchase_completed = await db.complete_purchase(user_id, config_id, price)
    except Exception:
        logger.exception("Completing purchase failed for user_id=%s config_id=%s", user_id, config_id)
        await callback.message.answer("❌ انجام خرید با خطا مواجه شد. دوباره تلاش کنید.")
        return None, None, False

    if not purchase_completed:
        await callback.message.answer(
            "⚠️ خرید انجام نشد؛ ممکن است موجودی کیف پول یا انبار تغییر کرده باشد. دوباره تلاش کنید."
        )
        return None, None, False
    return config_id, config_content, True


@router.callback_query(F.data.startswith("confirm_buy:"))
async def confirm_buy_handler(callback: CallbackQuery, db: DatabaseHandler) -> None:
    await callback.answer()
    if callback.from_user is None:
        return
    if callback.data is None:
        return
    parts = callback.data.split(":")
    if len(parts) != 2 or not parts[1].isdigit():
        await callback.message.answer("⚠️ درخواست خرید نامعتبر است.")
        return

    user_id = callback.from_user.id
    if not rate_limiter.allow(f"confirm_buy:{user_id}", 1.5):
        await callback.message.answer("⚠️ درخواست‌ها خیلی سریع ارسال شدند. لطفاً کمی بعد دوباره تلاش کنید.")
        return

    config_id = int(parts[1])

    try:
        snapshot = await db.get_model_config_purchase_snapshot(config_id)
    except Exception:
        logger.exception("Loading config snapshot failed for config_id=%s", config_id)
        await callback.message.answer("❌ بررسی وضعیت سرویس با خطا مواجه شد.")
        return

    if snapshot is None:
        await callback.message.answer("⚠️ این سرویس دیگر موجود نیست.")
        return

    _id, title, price, _duration, _description, _content, model, stock, is_active, is_sold = snapshot
    if is_active != 1:
        await callback.message.answer("این سرویس در حال حاضر غیرفعال است.")
        return
    if stock == 0 or is_sold == 1:
        await callback.message.answer("موجودی این سرویس به پایان رسیده است.")
        return

    try:
        balance = await db.get_user_balance(user_id)
    except Exception:
        logger.exception("Loading user balance failed for user_id=%s", user_id)
        await callback.message.answer("❌ بررسی موجودی کیف پول با خطا مواجه شد.")
        return

    if balance < price:
        shortage = price - balance
        await callback.message.answer(
            "❌ موجودی شما کافی نیست\n\n"
            f"💰 قیمت سرویس: {format_toman(price)} تومان\n"
            f"👛 موجودی فعلی شما: {format_toman(balance)} تومان\n"
            f"📉 مبلغ کسری: {format_toman(shortage)} تومان\n\n"
            "لطفاً ابتدا حساب خود را شارژ کنید.",
            reply_markup=build_insufficient_balance_menu(model),
        )
        return

    try:
        purchase_completed, config_content = await db.complete_model_purchase(user_id, config_id)
    except Exception:
        logger.exception("Completing model purchase failed for user_id=%s config_id=%s", user_id, config_id)
        await callback.message.answer("❌ انجام خرید با خطا مواجه شد. دوباره تلاش کنید.")
        return

    if not purchase_completed or not config_content:
        await callback.message.answer("⚠️ خرید انجام نشد؛ لطفاً دوباره تلاش کنید.")
        return

    try:
        config_details = await db.get_config_for_admin_edit(config_id)
        model = config_details[1] if config_details else ""
        await db.log_sale(
            user_id=user_id,
            username=callback.from_user.username,
            config_id=config_id,
            model=model,
            title=title,
            price=price,
        )
    except Exception:
        logger.exception("Sale logging failed for user_id=%s config_id=%s", user_id, config_id)

    await callback.message.answer(
        "✅ خرید با موفقیت انجام شد\n\n"
        "📦 سرویس شما:\n\n"
        f"{config_content}",
    )


@router.callback_query(F.data == "cancel_purchase_flow")
async def cancel_purchase_flow_handler(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer("❌ فرآیند خرید لغو شد.")


@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == "cancel_buy")
async def cancel_buy_handler(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer("❌ فرآیند خرید لغو شد.")


@router.callback_query(F.data == "my_services_menu")
async def my_services_menu_handler(callback: CallbackQuery, db: DatabaseHandler) -> None:
    await callback.answer()
    if callback.from_user is None:
        return

    user_id = callback.from_user.id
    try:
        services = await db.get_user_services(user_id)
    except Exception:
        logger.exception("Fetching active services failed for user_id=%s", user_id)
        await callback.message.answer("❌ دریافت سرویس‌های شما با خطا مواجه شد.")
        return

    if not services:
        await callback.message.answer(
            "📭 در حال حاضر هیچ سرویسی موجود نیست.",
            reply_markup=build_my_services_actions_keyboard(),
        )
        return

    lines = [f"📝 تعداد کل سرویس‌ها: {len(services)}", ""]
    for index, service in enumerate(services[:15], start=1):
        service_name = _normalize_service_text(service.get("name", "سرویس"))
        expires_at = _normalize_service_text(service.get("expires_at", "نامشخص"))
        config_link = _normalize_service_text(service.get("config_link", ""))
        lines.append(f"{index}) {service_name}")
        lines.append(f"⏳ انقضا: {expires_at}")
        lines.append(f"<code>{config_link or '—'}</code>")
        lines.append("")

    text = "\n".join(lines).strip()
    logger.debug("Prepared my services message for user_id=%s length=%s", user_id, len(text))

    chunks = _chunk_message(text)
    for index, chunk in enumerate(chunks):
        await callback.message.answer(
            chunk,
            parse_mode="HTML",
            reply_markup=build_my_services_actions_keyboard() if index == len(chunks) - 1 else None,
        )


@router.callback_query(F.data.startswith("purchase_info:"))
async def purchase_info_handler(callback: CallbackQuery, db: DatabaseHandler) -> None:
    await callback.answer()
    if callback.from_user is None:
        return

    config_id = parse_int_callback_payload(callback.data, "purchase_info:")
    if config_id is None:
        await callback.message.answer("⚠️ درخواست نامعتبر است.")
        return

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
    if not rate_limiter.allow(f"receipt_photo:{user.id}", 5.0):
        await message.answer("⚠️ درخواست‌ها خیلی سریع ارسال شدند. لطفاً کمی بعد دوباره تلاش کنید.")
        return

    state_data = await state.get_data()
    amount = int(state_data.get("recharge_amount", 0))
    if amount <= 0:
        await state.clear()
        await message.answer("⚠️ مبلغ شارژ پیدا نشد. لطفاً دوباره از بخش شارژ حساب شروع کنید.")
        return

    try:
        await db.add_user_if_not_exists(user.id)
        request_id = await db.create_recharge_request(
            user_id=user.id,
            username=user.username,
            amount=amount,
            receipt_file_id=message.photo[-1].file_id,
        )
        username_text = f"@{user.username}" if user.username else "ندارد"
        await bot.send_photo(
            chat_id=settings.ADMIN_ID,
            photo=message.photo[-1].file_id,
            caption=(
                "💳 درخواست شارژ جدید\n\n"
                f"👤 کاربر: {username_text}\n"
                f"🆔 ID: {user.id}\n\n"
                f"💰 مبلغ: {format_toman(amount)} تومان\n"
                f"🧾 شماره درخواست: {request_id}"
            ),
            reply_markup=build_receipt_review_keyboard(request_id).as_markup(),
        )
    except Exception:
        logger.exception("Forwarding receipt failed for user_id=%s", user.id)
        await message.answer("❌ ارسال فیش برای ادمین با خطا مواجه شد. دوباره تلاش کنید.")
        return

    await state.clear()
    await message.answer("✅ فیش شما دریافت شد و برای بررسی به ادمین ارسال شد.")


@router.message(RechargeStates.waiting_for_crypto_proof, F.photo)
async def crypto_proof_photo_handler(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db: DatabaseHandler,
) -> None:
    if message.from_user is None:
        return
    user = message.from_user
    if not rate_limiter.allow(f"crypto_proof_photo:{user.id}", 5.0):
        await message.answer("⚠️ درخواست‌ها خیلی سریع ارسال شدند. لطفاً کمی بعد دوباره تلاش کنید.")
        return
    try:
        await db.add_user_if_not_exists(user.id)
        request_id = await db.create_recharge_request(
            user_id=user.id,
            username=user.username,
            amount=0,
            receipt_file_id=message.photo[-1].file_id,
        )
        username_text = f"@{user.username}" if user.username else "ندارد"
        await bot.send_photo(
            chat_id=settings.ADMIN_ID,
            photo=message.photo[-1].file_id,
            caption=(
                "💱 درخواست شارژ ارزی جدید\n\n"
                f"👤 کاربر: {username_text}\n"
                f"🆔 ID: {user.id}\n\n"
                "🧾 مدرک: اسکرین‌شات تراکنش\n"
                f"🆔 شماره درخواست: {request_id}"
            ),
            reply_markup=build_receipt_review_keyboard(request_id).as_markup(),
        )
    except Exception:
        logger.exception("Forwarding crypto proof photo failed for user_id=%s", user.id)
        await message.answer("❌ ارسال مدرک با خطا مواجه شد. دوباره تلاش کنید.")
        return
    await state.clear()
    await message.answer("✅ ارسال شد و در انتظار بررسی ادمین است.")


@router.message(RechargeStates.waiting_for_crypto_proof, F.text)
async def crypto_proof_text_handler(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db: DatabaseHandler,
) -> None:
    if message.from_user is None:
        return
    if not rate_limiter.allow(f"crypto_proof_text:{message.from_user.id}", 5.0):
        await message.answer("⚠️ درخواست‌ها خیلی سریع ارسال شدند. لطفاً کمی بعد دوباره تلاش کنید.")
        return
    proof_hash = _sanitize_crypto_proof_text(message.text)
    if len(proof_hash) < 8:
        await message.answer("⚠️ هش تراکنش معتبر نیست. لطفاً متن کامل‌تری ارسال کنید.")
        return
    user = message.from_user
    try:
        await db.add_user_if_not_exists(user.id)
        request_id = await db.create_recharge_request(
            user_id=user.id,
            username=user.username,
            amount=0,
            receipt_file_id=f"crypto_hash:{proof_hash}",
        )
        username_text = f"@{user.username}" if user.username else "ندارد"
        await bot.send_message(
            chat_id=settings.ADMIN_ID,
            text=(
                "💱 درخواست شارژ ارزی جدید\n\n"
                f"👤 کاربر: {username_text}\n"
                f"🆔 ID: {user.id}\n\n"
                "🧾 مدرک: هش تراکنش\n"
                f"<code>{html.escape(proof_hash)}</code>\n\n"
                f"🆔 شماره درخواست: {request_id}"
            ),
            parse_mode="HTML",
            reply_markup=build_receipt_review_keyboard(request_id).as_markup(),
        )
    except Exception:
        logger.exception("Forwarding crypto hash proof failed for user_id=%s", user.id)
        await message.answer("❌ ارسال هش با خطا مواجه شد. دوباره تلاش کنید.")
        return
    await state.clear()
    await message.answer("✅ ارسال شد و در انتظار بررسی ادمین است.")


@router.message(RechargeStates.waiting_amount)
async def invalid_recharge_amount_handler(message: Message) -> None:
    await message.answer("⚠️ لطفاً مبلغ شارژ را فقط به‌صورت متنی و عددی ارسال کنید.")


@router.message(RechargeStates.waiting_for_receipt)
async def invalid_receipt_handler(message: Message) -> None:
    await message.answer("⚠️ لطفاً فقط عکس فیش واریزی را ارسال کنید.")


@router.message(RechargeStates.waiting_for_crypto_proof)
async def invalid_crypto_proof_handler(message: Message) -> None:
    await message.answer("⚠️ لطفاً هش تراکنش یا عکس اسکرین‌شات را ارسال کنید.")


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
        '<tg-emoji emoji-id="5444965061749644170">👨‍💻</tg-emoji> <b>• پشتیبانی</b>\n\n'
        '<tg-emoji emoji-id="6030646911269081346">📣</tg-emoji> • برای ارتباط با پشتیبانی به این شناسه پیام دهید:\n\n'
        '<tg-emoji emoji-id="5956392076387034439">💫</tg-emoji> • @NoxSupport1'
    )
    await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=builder.as_markup() if has_url_button else None,
    )
