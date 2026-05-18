from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from config import settings
from database.db_handler import DatabaseHandler
from keyboards.admin_menu import build_admin_menu
from keyboards.shop_menu import build_admin_category_price_menu
from keyboards.start_menu import build_start_menu
from utils.states import AdminPriceStates, AdminRechargeStates, AdminServiceStates, AdminStates

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


def _model_title(model: str) -> str:
    return "Nox Plus" if model == "nox_plus" else "Nox Multi"


def _stock_text(stock: int) -> str:
    if stock == -1:
        return "نامحدود"
    return str(stock)


def build_services_root_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="مدیریت Nox Plus", callback_data="admin_model:nox_plus"))
    builder.row(InlineKeyboardButton(text="مدیریت Nox Multi", callback_data="admin_model:nox_multi"))
    builder.row(InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_back:main_admin_menu"))
    return builder.as_markup()


def build_model_list_keyboard(
    model: str,
    configs: list[tuple[int, str, int, str, int, int]],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for config_id, title, price, duration, stock, is_active in configs:
        status = "✅ فعال" if is_active == 1 else "⛔ غیرفعال"
        info = (
            f"📦 {title or '-'}\n"
            f"💰 {price:,} | ⏳ {duration}\n"
            f"📦 موجودی: {_stock_text(stock)} | {status}"
        ).replace(",", "٬")
        builder.row(InlineKeyboardButton(text=info, callback_data=f"admin_edit_config:{config_id}"))
        builder.row(
            InlineKeyboardButton(text="✏️ ویرایش", callback_data=f"admin_edit_config:{config_id}"),
            InlineKeyboardButton(text="🗑 حذف", callback_data=f"admin_delete_config:{config_id}"),
            InlineKeyboardButton(text="✅ فعال/غیرفعال", callback_data=f"admin_toggle_config:{config_id}"),
        )

    if total_pages > 1:
        nav_buttons: list[InlineKeyboardButton] = []
        if page > 1:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="⬅️ قبلی",
                    callback_data=f"admin_model_page:{model}:{page-1}",
                )
            )
        nav_buttons.append(
            InlineKeyboardButton(
                text=f"{page}/{total_pages}",
                callback_data="admin_noop",
            )
        )
        if page < total_pages:
            nav_buttons.append(
                InlineKeyboardButton(
                    text="بعدی ➡️",
                    callback_data=f"admin_model_page:{model}:{page+1}",
                )
            )
        builder.row(*nav_buttons)

    builder.row(
        InlineKeyboardButton(text="➕ افزودن کانفیگ جدید", callback_data=f"admin_add_config:{model}")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_back:admin_services_root")
    )
    return builder.as_markup()


def build_edit_config_keyboard(config_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="تغییر عنوان", callback_data=f"admin_edit_field:{config_id}:title"))
    builder.row(InlineKeyboardButton(text="تغییر قیمت", callback_data=f"admin_edit_field:{config_id}:price"))
    builder.row(InlineKeyboardButton(text="تغییر مدت", callback_data=f"admin_edit_field:{config_id}:duration"))
    builder.row(
        InlineKeyboardButton(text="تغییر توضیحات", callback_data=f"admin_edit_field:{config_id}:description")
    )
    builder.row(InlineKeyboardButton(text="تغییر موجودی", callback_data=f"admin_edit_field:{config_id}:stock"))
    builder.row(
        InlineKeyboardButton(
            text="تغییر متن کانفیگ",
            callback_data=f"admin_edit_field:{config_id}:config_content",
        )
    )
    builder.row(
        InlineKeyboardButton(text="✅ فعال/غیرفعال", callback_data=f"admin_toggle_config:{config_id}")
    )
    builder.row(InlineKeyboardButton(text="🗑 حذف", callback_data=f"admin_delete_config:{config_id}"))
    return builder.as_markup()


def build_sales_report_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="refresh_sales_report"),
        InlineKeyboardButton(text="⬅️ بازگشت", callback_data="admin_back:main_admin_menu"),
    )
    return builder.as_markup()


async def _send_sales_report(message: Message, db: DatabaseHandler) -> None:
    today_sales = await db.get_today_sales_count()
    today_amount = await db.get_today_sales_amount()
    total_amount = await db.get_total_sales_amount()
    latest = await db.get_latest_sales(5)

    lines = [
        "📊 گزارش فروش",
        "",
        f"📅 فروش امروز: {today_sales}",
        f"💰 درآمد امروز: {today_amount:,} تومان".replace(",", "٬"),
        f"💎 کل درآمد: {total_amount:,} تومان".replace(",", "٬"),
        "",
        "آخرین خریدها:",
    ]
    if latest:
        numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        for idx, (username, model, _title, price, _purchased_at) in enumerate(latest):
            model_text = "Nox Plus" if model == "nox_plus" else "Nox Multi" if model == "nox_multi" else model
            username_text = f"@{username}" if username else "بدون‌نام"
            lines.append(
                f"{numbers[idx]} {username_text} | {model_text} | {price:,}".replace(",", "٬")
            )
    else:
        lines.append("موردی ثبت نشده است.")

    await message.answer("\n".join(lines), reply_markup=build_sales_report_keyboard())


async def _send_admin_edit_config(message: Message, db: DatabaseHandler, config_id: int) -> None:
    config = await db.get_config_for_admin_edit(config_id)
    if not config:
        await message.answer("⚠️ کانفیگ پیدا نشد.")
        return

    _, model, title, price, duration, description, stock, is_active, config_content = config
    status = "فعال" if is_active == 1 else "غیرفعال"
    await message.answer(
        f"جزئیات کانفیگ #{config_id}\n"
        f"مدل: {_model_title(model)}\n"
        f"عنوان: {title}\n"
        f"قیمت: {price:,} تومان\n"
        f"مدت: {duration}\n"
        f"توضیحات: {description}\n"
        f"موجودی: {_stock_text(stock)}\n"
        f"وضعیت: {status}\n\n"
        f"متن کانفیگ:\n{config_content}".replace(",", "٬"),
        reply_markup=build_edit_config_keyboard(config_id),
    )


@router.message(Command("admin"))
async def admin_panel_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "پنل ادمین فعال شد. یکی از گزینه‌های زیر را انتخاب کنید.",
        reply_markup=build_admin_menu(),
    )


@router.message(F.text == "مدیریت سرویس‌ها")
async def admin_services_root_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "مدیریت سرویس‌ها\nیکی از مدل‌ها را انتخاب کنید:",
        reply_markup=build_services_root_keyboard(),
    )


@router.callback_query(F.data == "admin_services_root")
async def admin_services_root_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.answer(
        "مدیریت سرویس‌ها\nیکی از مدل‌ها را انتخاب کنید:",
        reply_markup=build_services_root_keyboard(),
    )


async def _send_admin_model_page(
    message: Message,
    db: DatabaseHandler,
    model: str,
    page: int = 1,
) -> None:
    if model not in {"nox_plus", "nox_multi"}:
        await message.answer("⚠️ مدل نامعتبر است.")
        return

    page_size = 10
    total = await db.count_admin_configs(model)
    total_pages = max(1, (total + page_size - 1) // page_size)
    safe_page = min(max(1, page), total_pages)
    configs = await db.get_admin_configs(model=model, page=safe_page, page_size=page_size)

    model_name = _model_title(model)
    text = (
        f"مدیریت {model_name}\n"
        f"تعداد کل کانفیگ‌ها: {total}\n"
        "برای مدیریت، یکی از موارد زیر را انتخاب کنید:"
    )
    await message.answer(
        text,
        reply_markup=build_model_list_keyboard(model, configs, safe_page, total_pages),
    )


@router.callback_query(F.data.startswith("admin_model:"))
async def admin_model_handler(callback: CallbackQuery, db: DatabaseHandler, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    model = callback.data.split(":", 1)[1]
    try:
        await _send_admin_model_page(callback.message, db, model=model, page=1)
    except Exception:
        logger.exception("Loading admin model list failed for model=%s", model)
        await callback.message.answer("❌ دریافت لیست کانفیگ‌ها با خطا مواجه شد.")


@router.callback_query(F.data.startswith("admin_model_page:"))
async def admin_model_page_handler(callback: CallbackQuery, db: DatabaseHandler) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) != 3 or not parts[2].isdigit():
        await callback.message.answer("⚠️ صفحه نامعتبر است.")
        return
    model = parts[1]
    page = int(parts[2])
    try:
        await _send_admin_model_page(callback.message, db, model=model, page=page)
    except Exception:
        logger.exception("Loading paginated admin model list failed for model=%s page=%s", model, page)
        await callback.message.answer("❌ دریافت لیست کانفیگ‌ها با خطا مواجه شد.")


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


@router.message(F.text == "📊 گزارش فروش")
async def sales_report_from_sales_table_handler(message: Message, db: DatabaseHandler) -> None:
    try:
        await _send_sales_report(message, db)
    except Exception:
        logger.exception("Loading sales report from sales table failed")
        await message.answer("❌ دریافت گزارش فروش با خطا مواجه شد.")


@router.callback_query(F.data == "admin_sales_report")
async def admin_sales_report_callback_handler(callback: CallbackQuery, db: DatabaseHandler) -> None:
    await callback.answer()
    try:
        await _send_sales_report(callback.message, db)
    except Exception:
        logger.exception("Loading sales report callback failed")
        await callback.message.answer("❌ دریافت گزارش فروش با خطا مواجه شد.")


@router.callback_query(F.data == "refresh_sales_report")
async def refresh_sales_report_callback_handler(callback: CallbackQuery, db: DatabaseHandler) -> None:
    await callback.answer("بروزرسانی شد")
    try:
        await _send_sales_report(callback.message, db)
    except Exception:
        logger.exception("Refreshing sales report failed")
        await callback.message.answer("❌ بروزرسانی گزارش فروش با خطا مواجه شد.")


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


@router.callback_query(F.data.startswith("admin_add_config:"))
async def admin_add_config_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    model = callback.data.split(":", 1)[1]
    if model not in {"nox_plus", "nox_multi"}:
        await callback.message.answer("⚠️ مدل نامعتبر است.")
        return
    await state.set_state(AdminServiceStates.adding_config_field)
    await state.update_data(
        selected_model=model,
        add_step="title",
        add_payload={},
    )
    await callback.message.answer("عنوان کانفیگ را ارسال کنید:")


@router.message(AdminServiceStates.adding_config_field, F.text)
async def admin_add_config_field_handler(message: Message, state: FSMContext, db: DatabaseHandler) -> None:
    state_data = await state.get_data()
    model = state_data.get("selected_model")
    step = state_data.get("add_step")
    payload = dict(state_data.get("add_payload", {}))
    value = message.text.strip()

    if step == "title":
        if not value:
            await message.answer("⚠️ عنوان نمی‌تواند خالی باشد.")
            return
        payload["title"] = value
        await state.update_data(add_step="price", add_payload=payload)
        await message.answer("قیمت را به تومان ارسال کنید (عدد):")
        return

    if step == "price":
        normalized = value.replace("٬", "").replace(",", "")
        if not normalized.isdigit():
            await message.answer("⚠️ قیمت باید عدد صحیح و بزرگ‌تر یا مساوی صفر باشد.")
            return
        payload["price"] = int(normalized)
        await state.update_data(add_step="duration", add_payload=payload)
        await message.answer("مدت سرویس را ارسال کنید (مثال: 30 روز):")
        return

    if step == "duration":
        if not value:
            await message.answer("⚠️ مدت نمی‌تواند خالی باشد.")
            return
        payload["duration"] = value
        await state.update_data(add_step="description", add_payload=payload)
        await message.answer("توضیحات را ارسال کنید:")
        return

    if step == "description":
        payload["description"] = value
        await state.update_data(add_step="stock", add_payload=payload)
        await message.answer("موجودی را ارسال کنید (-1 برای نامحدود):")
        return

    if step == "stock":
        normalized = value.replace("٬", "").replace(",", "")
        is_number = normalized.startswith("-") and normalized[1:].isdigit() or normalized.isdigit()
        if not is_number:
            await message.answer("⚠️ موجودی باید عدد باشد. برای نامحدود مقدار -1 را بفرستید.")
            return
        stock = int(normalized)
        if stock < -1:
            await message.answer("⚠️ مقدار موجودی نمی‌تواند کمتر از -1 باشد.")
            return
        payload["stock"] = stock
        await state.update_data(add_step="config_content", add_payload=payload)
        await message.answer("متن کانفیگ را ارسال کنید:")
        return

    if step == "config_content":
        if not value:
            await message.answer("⚠️ متن کانفیگ نمی‌تواند خالی باشد.")
            return
        payload["config_content"] = value
        model_name = _model_title(model)
        stock_text = _stock_text(int(payload["stock"]))

        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="تأیید", callback_data="admin_confirm_add_config"))
        builder.row(InlineKeyboardButton(text="انصراف", callback_data="admin_cancel_add_config"))

        await state.update_data(add_step="confirm", add_payload=payload)
        await message.answer(
            "پیش‌نمایش کانفیگ جدید:\n"
            f"مدل: {model_name}\n"
            f"عنوان: {payload['title']}\n"
            f"قیمت: {payload['price']:,} تومان\n"
            f"مدت: {payload['duration']}\n"
            f"توضیحات: {payload['description']}\n"
            f"موجودی: {stock_text}\n\n"
            f"متن کانفیگ:\n{payload['config_content']}".replace(",", "٬"),
            reply_markup=builder.as_markup(),
        )
        return


@router.callback_query(F.data == "admin_cancel_add_config")
async def admin_cancel_add_config_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await callback.message.answer("❌ افزودن کانفیگ لغو شد.", reply_markup=build_admin_menu())


@router.callback_query(F.data == "admin_confirm_add_config")
async def admin_confirm_add_config_handler(
    callback: CallbackQuery,
    state: FSMContext,
    db: DatabaseHandler,
) -> None:
    await callback.answer()
    state_data = await state.get_data()
    model = state_data.get("selected_model")
    payload = state_data.get("add_payload", {})
    required = {"title", "price", "duration", "description", "stock", "config_content"}
    if model not in {"nox_plus", "nox_multi"} or not required.issubset(payload.keys()):
        await state.clear()
        await callback.message.answer("⚠️ اطلاعات کافی برای ثبت کانفیگ موجود نیست.")
        return

    try:
        await db.add_model_config(
            model=model,
            title=str(payload["title"]),
            price=int(payload["price"]),
            duration=str(payload["duration"]),
            description=str(payload["description"]),
            stock=int(payload["stock"]),
            config_content=str(payload["config_content"]),
        )
    except Exception:
        logger.exception("Adding model config failed for model=%s", model)
        await callback.message.answer("❌ ثبت کانفیگ با خطا مواجه شد.")
        return

    await state.clear()
    await callback.message.answer("✅ کانفیگ جدید با موفقیت ثبت شد.")
    await _send_admin_model_page(callback.message, db, model=model, page=1)


@router.callback_query(F.data.startswith("admin_edit_config:"))
async def admin_edit_config_handler(callback: CallbackQuery, db: DatabaseHandler, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    config_id_text = callback.data.split(":", 1)[1]
    if not config_id_text.isdigit():
        await callback.message.answer("⚠️ شناسه کانفیگ نامعتبر است.")
        return
    config_id = int(config_id_text)
    await _send_admin_edit_config(callback.message, db, config_id)


@router.callback_query(F.data.startswith("admin_edit_field:"))
async def admin_edit_field_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) != 3 or not parts[1].isdigit():
        await callback.message.answer("⚠️ درخواست نامعتبر است.")
        return
    config_id = int(parts[1])
    field = parts[2]
    if field not in {"title", "price", "duration", "description", "stock", "config_content"}:
        await callback.message.answer("⚠️ فیلد نامعتبر است.")
        return
    await state.set_state(AdminServiceStates.editing_config_field)
    await state.update_data(editing_config_id=config_id, editing_field=field)
    await callback.message.answer("مقدار جدید را ارسال کنید:")


@router.message(AdminServiceStates.editing_config_field, F.text)
async def admin_edit_field_value_handler(message: Message, state: FSMContext, db: DatabaseHandler) -> None:
    state_data = await state.get_data()
    config_id = state_data.get("editing_config_id")
    field = state_data.get("editing_field")
    if not config_id or not field:
        await state.clear()
        await message.answer("⚠️ اطلاعات ویرایش ناقص است.")
        return

    raw = message.text.strip()
    if field in {"price", "stock"}:
        normalized = raw.replace("٬", "").replace(",", "")
        is_number = normalized.startswith("-") and normalized[1:].isdigit() or normalized.isdigit()
        if not is_number:
            await message.answer("⚠️ مقدار باید عدد باشد.")
            return
        value: int | str = int(normalized)
        if field == "price" and value < 0:
            await message.answer("⚠️ قیمت باید بزرگ‌تر یا مساوی صفر باشد.")
            return
        if field == "stock" and value < -1:
            await message.answer("⚠️ موجودی نمی‌تواند کمتر از -1 باشد.")
            return
    else:
        if not raw:
            await message.answer("⚠️ مقدار نمی‌تواند خالی باشد.")
            return
        value = raw

    try:
        updated = await db.update_model_config(int(config_id), str(field), value)
    except Exception:
        logger.exception("Updating config field failed for config_id=%s field=%s", config_id, field)
        await message.answer("❌ ویرایش با خطا مواجه شد.")
        return
    await state.clear()
    if not updated:
        await message.answer("⚠️ بروزرسانی انجام نشد.")
        return
    # Keep admin in the same edit context for a smoother UX after field updates.
    await message.answer("✅ مقدار با موفقیت بروزرسانی شد.")
    await _send_admin_edit_config(message, db, int(config_id))


@router.callback_query(F.data.startswith("admin_delete_config:"))
async def admin_delete_config_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    config_id_text = callback.data.split(":", 1)[1]
    if not config_id_text.isdigit():
        await callback.message.answer("⚠️ شناسه کانفیگ نامعتبر است.")
        return
    config_id = int(config_id_text)
    await state.set_state(AdminServiceStates.confirming_delete)
    await state.update_data(deleting_config_id=config_id)

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="بله، حذف کن", callback_data=f"admin_confirm_delete:{config_id}"))
    builder.row(InlineKeyboardButton(text="خیر", callback_data=f"admin_back:edit_config_menu:{config_id}"))
    await callback.message.answer(
        "آیا از حذف این کانفیگ مطمئن هستید؟",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(AdminServiceStates.confirming_delete, F.data.startswith("admin_confirm_delete:"))
async def admin_confirm_delete_handler(
    callback: CallbackQuery,
    state: FSMContext,
    db: DatabaseHandler,
) -> None:
    await callback.answer()
    config_id_text = callback.data.split(":", 1)[1]
    if not config_id_text.isdigit():
        await callback.message.answer("⚠️ شناسه کانفیگ نامعتبر است.")
        return
    config_id = int(config_id_text)
    config = await db.get_config_for_admin_edit(config_id)
    model = config[1] if config else "nox_plus"
    try:
        deleted = await db.delete_model_config(config_id)
    except Exception:
        logger.exception("Deleting model config failed for config_id=%s", config_id)
        await callback.message.answer("❌ حذف کانفیگ با خطا مواجه شد.")
        return
    await state.clear()
    if not deleted:
        await callback.message.answer("⚠️ کانفیگ برای حذف پیدا نشد.")
        return
    await callback.message.answer("✅ کانفیگ حذف شد.")
    await _send_admin_model_page(callback.message, db, model=model, page=1)


@router.callback_query(F.data.startswith("admin_toggle_config:"))
async def admin_toggle_config_handler(callback: CallbackQuery, db: DatabaseHandler) -> None:
    await callback.answer()
    config_id_text = callback.data.split(":", 1)[1]
    if not config_id_text.isdigit():
        await callback.message.answer("⚠️ شناسه کانفیگ نامعتبر است.")
        return
    config_id = int(config_id_text)
    config = await db.get_config_for_admin_edit(config_id)
    if not config:
        await callback.message.answer("⚠️ کانفیگ پیدا نشد.")
        return
    model = config[1]
    try:
        updated, is_active = await db.toggle_model_config_active(config_id)
    except Exception:
        logger.exception("Toggling config failed for config_id=%s", config_id)
        await callback.message.answer("❌ تغییر وضعیت با خطا مواجه شد.")
        return
    if not updated:
        await callback.message.answer("⚠️ تغییر وضعیت انجام نشد.")
        return
    status = "فعال" if is_active == 1 else "غیرفعال"
    await callback.message.answer(f"✅ وضعیت کانفیگ به «{status}» تغییر کرد.")
    await _send_admin_model_page(callback.message, db, model=model, page=1)


@router.callback_query(F.data.startswith("admin_back:"))
async def admin_back_handler(callback: CallbackQuery, state: FSMContext, db: DatabaseHandler) -> None:
    await callback.answer()
    await state.clear()
    target = callback.data.split(":", 1)[1]
    if target == "main_admin_menu":
        await callback.message.answer("منوی اصلی ادمین:", reply_markup=build_admin_menu())
        return
    if target == "admin_services_root":
        await callback.message.answer(
            "مدیریت سرویس‌ها\nیکی از مدل‌ها را انتخاب کنید:",
            reply_markup=build_services_root_keyboard(),
        )
        return
    if target.startswith("edit_config_menu:"):
        parts = target.split(":")
        if len(parts) == 2 and parts[1].isdigit():
            await _send_admin_edit_config(callback.message, db, int(parts[1]))
        return


@router.callback_query(F.data == "admin_noop")
async def admin_noop_handler(callback: CallbackQuery) -> None:
    await callback.answer()
