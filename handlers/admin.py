from __future__ import annotations

import asyncio
import html
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
from handlers.main_menu_renderer import render_main_menu
from utils.states import AdminServiceStates, AdminStates
from utils.security import parse_int_callback_payload, rate_limiter

logger = logging.getLogger(__name__)

router = Router(name="admin")
router.message.filter(F.from_user.id == settings.ADMIN_ID)
router.callback_query.filter(F.from_user.id == settings.ADMIN_ID)


def format_toman(amount: int) -> str:
    return f"{amount:,}".replace(",", "٬")


RECHARGE_PAGE_SIZE = 5
BROADCAST_CONCURRENCY = 30
CRYPTO_WALLET_KEYS: dict[str, str] = {
    "crypto_usdt_bep20": "USDT (BEP20)",
    "crypto_tron_trc20": "TRON (TRC20)",
    "crypto_ton": "TON",
}
CRYPTO_APPROVE_CANCEL_TEXT = "❌ لغو تایید شارژ ارزی"


def _format_recharge_status(status: str) -> str:
    return {
        "pending": "🟡 pending",
        "approved": "✅ approved",
        "rejected": "❌ rejected",
    }.get(status, status)


def build_recharge_requests_keyboard(
    status: str,
    page: int,
    total_pages: int,
    request_ids: list[int],
    user_id: int | None = None,
    username: str | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    filters = [
        ("همه", "all"),
        ("pending", "pending"),
        ("approved", "approved"),
        ("rejected", "rejected"),
    ]
    for text, value in filters:
        prefix = "✅ " if status == value else ""
        builder.button(
            text=f"{prefix}{text}",
            callback_data=(
                f"recharge_admin_list:status={value}:page=1"
                f":uid={user_id or ''}:uname={username or ''}"
            ),
        )
    builder.adjust(4)
    builder.row(
        InlineKeyboardButton(
            text="🔎 جستجو user_id",
            callback_data=f"recharge_admin_search:user_id:status={status}",
        ),
        InlineKeyboardButton(
            text="🔎 جستجو username",
            callback_data=f"recharge_admin_search:username:status={status}",
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🧹 حذف جستجو",
            callback_data=f"recharge_admin_list:status={status}:page=1:uid=:uname=",
        )
    )
    for request_id in request_ids:
        builder.row(
            InlineKeyboardButton(
                text=f"📄 جزئیات درخواست #{request_id}",
                callback_data=(
                    f"recharge_admin_open:{request_id}:status={status}:page={page}"
                    f":uid={user_id or ''}:uname={username or ''}"
                ),
            )
        )

    nav_buttons: list[InlineKeyboardButton] = []
    if page > 1:
        nav_buttons.append(
            InlineKeyboardButton(
                text="⬅️ قبلی",
                callback_data=(
                    f"recharge_admin_list:status={status}:page={page-1}"
                    f":uid={user_id or ''}:uname={username or ''}"
                ),
            )
        )
    nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="admin_noop"))
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton(
                text="➡️ بعدی",
                callback_data=(
                    f"recharge_admin_list:status={status}:page={page+1}"
                    f":uid={user_id or ''}:uname={username or ''}"
                ),
            )
        )
    builder.row(*nav_buttons)
    builder.row(
        InlineKeyboardButton(text="📊 گزارش شارژ", callback_data="recharge_admin_report"),
        InlineKeyboardButton(text="🔙 منوی ادمین", callback_data="admin_back:main_admin_menu"),
    )
    return builder.as_markup()


def build_recharge_request_details_keyboard(request_id: int, status: str, back_payload: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if status == "pending":
        builder.row(
            InlineKeyboardButton(text="✅ تایید", callback_data=f"recharge_admin_approve:{request_id}:{back_payload}"),
            InlineKeyboardButton(text="⛔ رد", callback_data=f"recharge_admin_reject:{request_id}:{back_payload}"),
        )
    builder.row(
        InlineKeyboardButton(text="⬅️ بازگشت به لیست", callback_data=f"recharge_admin_list:{back_payload}")
    )
    return builder.as_markup()


def _parse_recharge_list_payload(payload: str) -> tuple[str, int, int | None, str | None]:
    status = "all"
    page = 1
    user_id: int | None = None
    username: str | None = None
    for chunk in payload.split(":"):
        if "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        if key == "status" and value in {"all", "pending", "approved", "rejected"}:
            status = value
        elif key == "page" and value.isdigit():
            page = max(1, int(value))
        elif key == "uid" and value.isdigit():
            user_id = int(value)
        elif key == "uname" and value:
            username = value
    return status, page, user_id, username


async def _send_recharge_requests_page(message: Message, db: DatabaseHandler, payload: str) -> None:
    status, page, user_id, username = _parse_recharge_list_payload(payload)
    db_status = None if status == "all" else status

    total = await db.count_recharge_requests(status=db_status, user_id=user_id, username=username)
    total_pages = max(1, (total + RECHARGE_PAGE_SIZE - 1) // RECHARGE_PAGE_SIZE)
    safe_page = min(page, total_pages)
    requests = await db.get_recharge_requests(
        status=db_status,
        user_id=user_id,
        username=username,
        page=safe_page,
        limit=RECHARGE_PAGE_SIZE,
    )

    title = f"📥 درخواست‌های شارژ — {status}"
    if user_id is not None:
        title += f" | user_id={user_id}"
    if username:
        title += f" | username~{username}"

    lines = [title, ""]
    if not requests:
        lines.append("موردی برای نمایش وجود ندارد.")
    else:
        for request_id, req_user_id, req_username, amount, _file_id, req_status, created_at in requests:
            username_text = f"@{req_username}" if req_username else "ندارد"
            lines.append(
                f"🧾 ID: {request_id}\n"
                f"👤 {username_text} (user_id: {req_user_id})\n"
                f"💰 مبلغ: {format_toman(amount)} تومان\n"
                f"🕒 ثبت: {created_at}\n"
                f"📌 وضعیت: {_format_recharge_status(req_status)}"
            )
            lines.append("────────────")
    lines.append(f"صفحه {safe_page} از {total_pages}")

    await message.answer(
        "\n".join(lines),
        reply_markup=build_recharge_requests_keyboard(
            status=status,
            page=safe_page,
            total_pages=total_pages,
            request_ids=[item[0] for item in requests],
            user_id=user_id,
            username=username,
        ),
    )


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


def build_crypto_approve_cancel_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=CRYPTO_APPROVE_CANCEL_TEXT, callback_data="admin_cancel_crypto_approve"))
    return builder.as_markup()


def _is_crypto_recharge_request(amount: int, receipt_file_id: str) -> bool:
    return amount == 0 or receipt_file_id.startswith("crypto_hash:")


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
    builder.row(InlineKeyboardButton(text="تغییر سرعت", callback_data=f"admin_edit_field:{config_id}:speed"))
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


def build_finish_collecting_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ اتمام کار", callback_data="admin_finish_collecting_configs"))
    return builder.as_markup()


def build_crypto_wallets_manage_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, title in CRYPTO_WALLET_KEYS.items():
        builder.row(
            InlineKeyboardButton(
                text=f"✏️ ویرایش {title}",
                callback_data=f"admin_crypto_wallet_edit:{key}",
            )
        )
    builder.row(InlineKeyboardButton(text="🔙 منوی ادمین", callback_data="admin_back:main_admin_menu"))
    return builder.as_markup()


async def _broadcast_one(
    bot: Bot,
    semaphore: asyncio.Semaphore,
    *,
    user_id: int,
    source_chat_id: int,
    source_message_id: int,
) -> bool:
    async with semaphore:
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=source_chat_id,
                message_id=source_message_id,
            )
            return True
        except Exception:
            return False


async def _send_crypto_wallets_manage_panel(message: Message, db: DatabaseHandler) -> None:
    wallet_usdt = await db.get_setting("crypto_usdt_bep20", "تنظیم نشده")
    wallet_tron = await db.get_setting("crypto_tron_trc20", "تنظیم نشده")
    wallet_ton = await db.get_setting("crypto_ton", "تنظیم نشده")
    await message.answer(
        "💱 مدیریت ولت‌های ارزی\n\n"
        f"USDT (BEP20):\n<code>{html.escape(str(wallet_usdt))}</code>\n\n"
        f"TRON (TRC20):\n<code>{html.escape(str(wallet_tron))}</code>\n\n"
        f"TON:\n<code>{html.escape(str(wallet_ton))}</code>",
        parse_mode="HTML",
        reply_markup=build_crypto_wallets_manage_keyboard(),
    )


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

    _, model, title, price, duration, speed, description, stock, is_active, config_content = config
    status = "فعال" if is_active == 1 else "غیرفعال"
    await message.answer(
        f"جزئیات کانفیگ #{config_id}\n"
        f"مدل: {_model_title(model)}\n"
        f"عنوان: {title}\n"
        f"قیمت: {price:,} تومان\n"
        f"مدت: {duration}\n"
        f"سرعت: {speed}\n"
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


@router.message(F.text == "🚪 خروج از پنل مدیریت")
async def admin_exit_panel_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🏠 شما از پنل مدیریت خارج شدید.", reply_markup=ReplyKeyboardRemove())
    await render_main_menu(message)


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


@router.message(F.text == "📥 درخواست‌های شارژ")
async def recharge_requests_menu_handler(message: Message, state: FSMContext, db: DatabaseHandler) -> None:
    await state.clear()
    try:
        pending_count = await db.get_pending_recharge_count()
        await message.answer(f"📥 پنل درخواست‌های شارژ\n🟡 در انتظار بررسی: {pending_count}")
        await _send_recharge_requests_page(message, db, "status=all:page=1:uid=:uname=")
    except Exception:
        logger.exception("Loading recharge requests menu failed")
        await message.answer("❌ دریافت درخواست‌های شارژ با خطا مواجه شد.")


@router.callback_query(F.data.startswith("recharge_admin_list:"))
async def recharge_admin_list_handler(callback: CallbackQuery, state: FSMContext, db: DatabaseHandler) -> None:
    await callback.answer()
    await state.clear()
    payload = callback.data.split("recharge_admin_list:", 1)[1]
    try:
        await _send_recharge_requests_page(callback.message, db, payload)
    except Exception:
        logger.exception("Loading recharge list callback failed payload=%s", payload)
        await callback.message.answer("❌ دریافت لیست درخواست‌ها با خطا مواجه شد.")


@router.callback_query(F.data.startswith("recharge_admin_search:"))
async def recharge_admin_search_start_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.message.answer("⚠️ درخواست جستجو نامعتبر است.")
        return
    search_type = parts[1]
    status = "all"
    if "=" in parts[2]:
        key, value = parts[2].split("=", 1)
        if key == "status" and value in {"all", "pending", "approved", "rejected"}:
            status = value

    await state.update_data(recharge_search_status=status)
    if search_type == "user_id":
        await state.set_state(AdminStates.waiting_recharge_search_user_id)
        await callback.message.answer("🔎 user_id را ارسال کنید:")
        return
    if search_type == "username":
        await state.set_state(AdminStates.waiting_recharge_search_username)
        await callback.message.answer("🔎 username را بدون @ ارسال کنید:")
        return
    await callback.message.answer("⚠️ نوع جستجو نامعتبر است.")


@router.message(AdminStates.waiting_recharge_search_user_id, F.text)
async def recharge_search_user_id_handler(message: Message, state: FSMContext, db: DatabaseHandler) -> None:
    raw_user_id = message.text.strip()
    if not raw_user_id.isdigit():
        await message.answer("⚠️ user_id باید عددی باشد.")
        return
    state_data = await state.get_data()
    status = state_data.get("recharge_search_status", "all")
    await state.clear()
    payload = f"status={status}:page=1:uid={int(raw_user_id)}:uname="
    await _send_recharge_requests_page(message, db, payload)


@router.message(AdminStates.waiting_recharge_search_username, F.text)
async def recharge_search_username_handler(message: Message, state: FSMContext, db: DatabaseHandler) -> None:
    username = message.text.strip().lstrip("@")
    if len(username) < 2:
        await message.answer("⚠️ username معتبر نیست.")
        return
    state_data = await state.get_data()
    status = state_data.get("recharge_search_status", "all")
    await state.clear()
    payload = f"status={status}:page=1:uid=:uname={username}"
    await _send_recharge_requests_page(message, db, payload)


@router.callback_query(F.data.startswith("recharge_admin_open:"))
async def recharge_admin_open_handler(callback: CallbackQuery, db: DatabaseHandler, bot: Bot) -> None:
    await callback.answer()
    parts = callback.data.split(":", 2)
    if len(parts) != 3 or not parts[1].isdigit():
        await callback.message.answer("⚠️ شناسه درخواست نامعتبر است.")
        return
    request_id = int(parts[1])
    back_payload = parts[2]

    request = await db.get_recharge_request(request_id)
    if not request:
        await callback.message.answer("⚠️ درخواست شارژ پیدا نشد.")
        return

    _id, user_id, username, amount, receipt_file_id, status, created_at = request
    username_text = f"@{username}" if username else "ندارد"
    caption = (
        "📄 جزئیات درخواست شارژ\n\n"
        f"🧾 ID: {request_id}\n"
        f"👤 کاربر: {username_text}\n"
        f"🆔 user_id: {user_id}\n"
        f"💰 مبلغ: {format_toman(amount)} تومان\n"
        f"📌 وضعیت: {_format_recharge_status(status)}\n"
        f"🕒 تاریخ ثبت: {created_at}"
    )
    keyboard = build_recharge_request_details_keyboard(request_id, status, back_payload)

    if receipt_file_id:
        try:
            await callback.message.answer_photo(photo=receipt_file_id, caption=caption, reply_markup=keyboard)
            return
        except Exception:
            logger.exception("Sending receipt photo failed for request_id=%s", request_id)
    await callback.message.answer(
        caption + "\n\n⚠️ نمایش تصویر رسید ممکن نبود.",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("recharge_admin_approve:"))
async def recharge_admin_approve_handler(
    callback: CallbackQuery,
    db: DatabaseHandler,
    bot: Bot,
    state: FSMContext,
) -> None:
    await callback.answer()
    if callback.from_user is None or callback.from_user.id != settings.ADMIN_ID:
        logger.warning("Unauthorized recharge approve attempt from user_id=%s", callback.from_user.id if callback.from_user else None)
        return
    if not rate_limiter.allow(f"admin_recharge_approve:{callback.from_user.id}", 1.0):
        await callback.message.answer("⚠️ درخواست‌ها خیلی سریع ارسال شدند. لطفاً کمی بعد دوباره تلاش کنید.")
        return
    parts = callback.data.split(":", 2)
    if len(parts) != 3 or not parts[1].isdigit():
        await callback.message.answer("⚠️ شناسه درخواست نامعتبر است.")
        return
    request_id = int(parts[1])
    back_payload = parts[2]

    request = await db.get_recharge_request(request_id)
    if not request:
        await callback.message.answer("⚠️ درخواست شارژ پیدا نشد.")
        return
    _id, _user_id, _username, amount, receipt_file_id, status, _created_at = request
    if status != "pending":
        await callback.message.answer("⚠️ این درخواست قبلاً بررسی شده است یا وجود ندارد.")
        return

    if _is_crypto_recharge_request(amount=amount, receipt_file_id=receipt_file_id):
        await state.set_state(AdminStates.waiting_for_crypto_approve_amount)
        await state.update_data(
            crypto_approve_request_id=request_id,
            crypto_approve_back_payload=back_payload,
        )
        await callback.message.answer(
            "💱 این درخواست مربوط به شارژ ارزی است.\n"
            "لطفاً مبلغ نهایی شارژ را به تومان وارد کنید:",
            reply_markup=build_crypto_approve_cancel_keyboard(),
        )
        return

    try:
        approved, user_id, amount = await db.approve_recharge_request(request_id)
    except Exception:
        logger.exception("Approving recharge from admin panel failed request_id=%s", request_id)
        await callback.message.answer("❌ تایید درخواست با خطا مواجه شد.")
        return

    if not approved:
        await callback.message.answer("⚠️ این درخواست قبلاً بررسی شده است یا وجود ندارد.")
        return

    new_balance = await db.get_user_balance(int(user_id))
    await bot.send_message(
        int(user_id),
        "✅ شارژ حساب شما تایید شد\n\n"
        f"💰 مبلغ شارژ: {format_toman(int(amount))} تومان\n"
        f"👛 موجودی جدید: {format_toman(new_balance)} تومان",
    )
    await callback.message.answer(f"✅ درخواست #{request_id} تایید شد.")
    await _send_recharge_requests_page(callback.message, db, back_payload)


@router.callback_query(F.data.startswith("recharge_admin_reject:"))
async def recharge_admin_reject_handler(callback: CallbackQuery, db: DatabaseHandler, bot: Bot) -> None:
    await callback.answer()
    if callback.from_user is None or callback.from_user.id != settings.ADMIN_ID:
        logger.warning("Unauthorized recharge reject attempt from user_id=%s", callback.from_user.id if callback.from_user else None)
        return
    if not rate_limiter.allow(f"admin_recharge_reject:{callback.from_user.id}", 1.0):
        await callback.message.answer("⚠️ درخواست‌ها خیلی سریع ارسال شدند. لطفاً کمی بعد دوباره تلاش کنید.")
        return
    parts = callback.data.split(":", 2)
    if len(parts) != 3 or not parts[1].isdigit():
        await callback.message.answer("⚠️ شناسه درخواست نامعتبر است.")
        return
    request_id = int(parts[1])
    back_payload = parts[2]

    try:
        rejected, user_id = await db.reject_recharge_request(request_id)
    except Exception:
        logger.exception("Rejecting recharge from admin panel failed request_id=%s", request_id)
        await callback.message.answer("❌ رد درخواست با خطا مواجه شد.")
        return

    if not rejected:
        await callback.message.answer("⚠️ این درخواست قبلاً بررسی شده است یا وجود ندارد.")
        return

    await bot.send_message(
        int(user_id),
        "❌ درخواست شارژ شما رد شد.\n\n"
        "در صورت بروز مشکل با پشتیبانی تماس بگیرید.",
    )
    await callback.message.answer(f"⛔ درخواست #{request_id} رد شد.")
    await _send_recharge_requests_page(callback.message, db, back_payload)


@router.callback_query(F.data == "admin_cancel_crypto_approve")
async def cancel_crypto_approve_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if await state.get_state() != AdminStates.waiting_for_crypto_approve_amount.state:
        await callback.message.answer("⚠️ عملیات فعالی برای لغو وجود ندارد.")
        return
    await state.clear()
    await callback.message.answer("❌ تایید شارژ ارزی لغو شد.", reply_markup=build_admin_menu())


@router.message(F.text == CRYPTO_APPROVE_CANCEL_TEXT, StateFilter(AdminStates.waiting_for_crypto_approve_amount))
async def cancel_crypto_approve_message_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("❌ تایید شارژ ارزی لغو شد.", reply_markup=build_admin_menu())


@router.message(AdminStates.waiting_for_crypto_approve_amount, F.text)
async def approve_crypto_recharge_amount_handler(
    message: Message,
    state: FSMContext,
    db: DatabaseHandler,
    bot: Bot,
) -> None:
    raw_amount = message.text.strip().replace("٬", "").replace(",", "")
    if not raw_amount.isdigit():
        await message.answer("⚠️ لطفاً مبلغ را فقط به‌صورت عددی وارد کنید.")
        return
    approved_amount = int(raw_amount)
    if approved_amount <= 0:
        await message.answer("⚠️ مبلغ باید بزرگ‌تر از صفر باشد.")
        return

    state_data = await state.get_data()
    request_id = state_data.get("crypto_approve_request_id")
    back_payload = state_data.get("crypto_approve_back_payload")
    if not request_id or not back_payload:
        await state.clear()
        await message.answer("⚠️ اطلاعات تایید ارزی ناقص است.", reply_markup=build_admin_menu())
        return

    request = await db.get_recharge_request(int(request_id))
    if not request:
        await state.clear()
        await message.answer("⚠️ درخواست شارژ پیدا نشد.", reply_markup=build_admin_menu())
        return
    _id, user_id, _username, amount, receipt_file_id, status, _created_at = request
    if status != "pending":
        await state.clear()
        await message.answer("⚠️ این درخواست دیگر در وضعیت pending نیست.", reply_markup=build_admin_menu())
        return
    if not _is_crypto_recharge_request(amount=amount, receipt_file_id=receipt_file_id):
        await state.clear()
        await message.answer("⚠️ این درخواست شارژ ارزی نیست.", reply_markup=build_admin_menu())
        return

    try:
        approved, approved_user_id, credited_amount = await db.approve_recharge_request(
            int(request_id),
            approved_amount=approved_amount,
        )
    except Exception:
        logger.exception("Approving crypto recharge with custom amount failed request_id=%s", request_id)
        await message.answer("❌ تایید درخواست شارژ ارزی با خطا مواجه شد.")
        return

    if not approved or approved_user_id is None or credited_amount is None:
        await state.clear()
        await message.answer("⚠️ این درخواست قبلاً بررسی شده است یا وجود ندارد.", reply_markup=build_admin_menu())
        return

    await state.clear()
    await bot.send_message(
        int(approved_user_id),
        "✅ شارژ ارزی حساب شما تایید شد.\n"
        f"مبلغ {format_toman(int(credited_amount))} تومان به کیف پول شما اضافه شد.",
    )
    await message.answer(
        f"✅ درخواست شارژ ارزی با موفقیت تایید شد و مبلغ {format_toman(int(credited_amount))} تومان به کیف پول کاربر اضافه شد."
    )
    await _send_recharge_requests_page(message, db, str(back_payload))


@router.message(F.text == "📊 گزارش شارژ")
async def recharge_report_handler(message: Message, db: DatabaseHandler) -> None:
    try:
        stats = await db.get_recharge_stats_today_and_total()
        latest_requests = await db.get_recharge_requests(status=None, page=1, limit=5)
    except Exception:
        logger.exception("Loading recharge report failed")
        await message.answer("❌ دریافت گزارش شارژ با خطا مواجه شد.")
        return

    lines = [
        "📊 گزارش شارژ",
        "",
        f"امروز: {stats.get('today_count', 0)} درخواست | مجموع: {format_toman(stats.get('today_amount', 0))} تومان",
        f"کلی: {stats.get('total_count', 0)} درخواست | مجموع: {format_toman(stats.get('total_amount', 0))} تومان",
        "",
        "آخرین درخواست‌ها:",
    ]
    if latest_requests:
        for request_id, user_id, username, amount, _file_id, status, _created_at in latest_requests:
            username_text = f"@{username}" if username else str(user_id)
            lines.append(
                f"• #{request_id} | {username_text} | {format_toman(amount)} | {_format_recharge_status(status)}"
            )
    else:
        lines.append("موردی ثبت نشده است.")

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📥 مشاهده درخواست‌ها", callback_data="recharge_admin_list:status=all:page=1:uid=:uname="))
    builder.row(InlineKeyboardButton(text="🔙 منوی ادمین", callback_data="admin_back:main_admin_menu"))
    await message.answer("\n".join(lines), reply_markup=builder.as_markup())


@router.callback_query(F.data == "recharge_admin_report")
async def recharge_report_callback_handler(callback: CallbackQuery, db: DatabaseHandler) -> None:
    await callback.answer()
    await recharge_report_handler(callback.message, db)


@router.message(F.text == "📊 گزارش فروش")
async def sales_report_from_sales_table_handler(message: Message, db: DatabaseHandler) -> None:
    try:
        await _send_sales_report(message, db)
    except Exception:
        logger.exception("Loading sales report from sales table failed")
        await message.answer("❌ دریافت گزارش فروش با خطا مواجه شد.")


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
    if callback.from_user is None or callback.from_user.id != settings.ADMIN_ID:
        logger.warning("Unauthorized broadcast confirm attempt from user_id=%s", callback.from_user.id if callback.from_user else None)
        return
    if not rate_limiter.allow(f"admin_broadcast:{callback.from_user.id}", 10.0):
        await callback.message.answer("⚠️ درخواست‌ها خیلی سریع ارسال شدند. لطفاً کمی بعد دوباره تلاش کنید.")
        return
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

    source_chat = int(source_chat_id)
    source_message = int(source_message_id)
    semaphore = asyncio.Semaphore(BROADCAST_CONCURRENCY)
    tasks = [
        asyncio.create_task(
            _broadcast_one(
                bot,
                semaphore,
                user_id=user_id,
                source_chat_id=source_chat,
                source_message_id=source_message,
            )
        )
        for user_id in user_ids
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    success_count = sum(1 for item in results if item is True)
    failed_count = len(results) - success_count

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


@router.message(F.text == "💳 مدیریت پرداخت")
async def payment_management_handler(message: Message, db: DatabaseHandler) -> None:
    card_number, card_holder_name = await db.get_payment_settings()
    shown_card = card_number or settings.ADMIN_CARD_NUMBER
    shown_name = card_holder_name or "تنظیم نشده"

    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="ویرایش شماره کارت"))
    builder.row(KeyboardButton(text="ویرایش نام صاحب کارت"))
    builder.row(KeyboardButton(text="🔙 بازگشت به منوی ادمین"))
    await message.answer(
        "💳 مدیریت پرداخت\n\n"
        f"شماره کارت فعلی: `{shown_card}`\n"
        f"نام صاحب کارت: {shown_name}",
        parse_mode="Markdown",
        reply_markup=builder.as_markup(resize_keyboard=True),
    )


@router.message(F.text == "<emoji id=6224341518182784992>🎁</emoji> مدیریت پاداش دعوت")
async def referral_reward_management_handler(message: Message, state: FSMContext, db: DatabaseHandler) -> None:
    await state.clear()
    reward_raw = await db.get_setting("referral_reward_amount", "2000")
    try:
        reward_amount = max(0, int(str(reward_raw or "0")))
    except ValueError:
        reward_amount = 0

    inline_builder = InlineKeyboardBuilder()
    inline_builder.row(
        InlineKeyboardButton(
            text="✏️ ویرایش مبلغ پاداش دعوت",
            callback_data="admin_edit_referral_reward",
        )
    )
    inline_builder.row(
        InlineKeyboardButton(
            text="🔙 منوی ادمین",
            callback_data="admin_back:main_admin_menu",
        )
    )
    await message.answer(
        "🎁 مدیریت پاداش دعوت\n\n"
        f"مبلغ فعلی پاداش: `{format_toman(reward_amount)}` تومان\n\n"
        "برای تغییر، گزینه ویرایش را انتخاب کنید.",
        parse_mode="Markdown",
        reply_markup=inline_builder.as_markup(),
    )


@router.callback_query(F.data == "admin_edit_referral_reward")
async def referral_reward_edit_start_callback_handler(
    callback: CallbackQuery,
    state: FSMContext,
    db: DatabaseHandler,
) -> None:
    await callback.answer()
    reward_raw = await db.get_setting("referral_reward_amount", "2000")
    try:
        reward_amount = max(0, int(str(reward_raw or "0")))
    except ValueError:
        reward_amount = 0

    await state.set_state(AdminStates.waiting_for_referral_reward_amount)
    await callback.message.answer(
        "🎁 مدیریت پاداش دعوت\n\n"
        f"مبلغ فعلی پاداش:\n{format_toman(reward_amount)} تومان\n\n"
        "مبلغ جدید را ارسال کنید.",
    )


@router.message(F.text == "✏️ ویرایش مبلغ پاداش دعوت")
async def referral_reward_edit_start_handler(message: Message, state: FSMContext, db: DatabaseHandler) -> None:
    reward_raw = await db.get_setting("referral_reward_amount", "2000")
    try:
        reward_amount = max(0, int(str(reward_raw or "0")))
    except ValueError:
        reward_amount = 0

    await state.set_state(AdminStates.waiting_for_referral_reward_amount)
    await message.answer(
        "🎁 ویرایش پاداش دعوت\n"
        f"مبلغ فعلی: `{format_toman(reward_amount)}` تومان\n\n"
        "مبلغ جدید را به تومان و فقط به‌صورت عددی ارسال کنید.",
        parse_mode="Markdown",
    )


@router.message(AdminStates.waiting_for_referral_reward_amount, F.text)
async def referral_reward_set_amount_handler(message: Message, state: FSMContext, db: DatabaseHandler) -> None:
    amount_text = message.text.strip().replace("٬", "").replace(",", "")
    if not amount_text.isdigit():
        await message.answer("⚠️ مبلغ نامعتبر است. لطفاً فقط عدد ارسال کنید.")
        return

    amount = int(amount_text)
    if amount < 0:
        await message.answer("⚠️ مبلغ نمی‌تواند منفی باشد.")
        return

    try:
        await db.update_setting("referral_reward_amount", str(amount))
    except Exception:
        logger.exception("Updating referral reward amount failed")
        await message.answer("❌ ذخیره مبلغ پاداش دعوت با خطا مواجه شد.")
        return

    await state.clear()
    await message.answer(
        f"✅ مبلغ پاداش دعوت با موفقیت به `{format_toman(amount)}` تومان تغییر کرد.",
        parse_mode="Markdown",
        reply_markup=build_admin_menu(),
    )


@router.message(F.text == "💱 مدیریت ولت‌های ارزی")
async def crypto_wallets_management_handler(message: Message, state: FSMContext, db: DatabaseHandler) -> None:
    await state.clear()
    await _send_crypto_wallets_manage_panel(message, db)


@router.callback_query(F.data.startswith("admin_crypto_wallet_edit:"))
async def crypto_wallet_edit_start_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    wallet_key = callback.data.split(":", 1)[1]
    if wallet_key not in CRYPTO_WALLET_KEYS:
        await callback.message.answer("⚠️ ولت نامعتبر است.")
        return
    await state.set_state(AdminStates.waiting_for_crypto_wallet_value)
    await state.update_data(crypto_wallet_key=wallet_key)
    await callback.message.answer(
        f"آدرس جدید {CRYPTO_WALLET_KEYS[wallet_key]} را ارسال کنید:",
    )


@router.message(AdminStates.waiting_for_crypto_wallet_value, F.text)
async def set_crypto_wallet_value_handler(message: Message, state: FSMContext, db: DatabaseHandler) -> None:
    wallet_value = message.text.strip()
    if len(wallet_value) < 4:
        await message.answer("⚠️ آدرس ولت معتبر نیست.")
        return
    state_data = await state.get_data()
    wallet_key = state_data.get("crypto_wallet_key")
    if wallet_key not in CRYPTO_WALLET_KEYS:
        await state.clear()
        await message.answer("⚠️ کلید ولت نامعتبر است.", reply_markup=build_admin_menu())
        return
    try:
        await db.update_setting(str(wallet_key), wallet_value)
    except Exception:
        logger.exception("Updating crypto wallet failed key=%s", wallet_key)
        await message.answer("❌ ذخیره آدرس ولت با خطا مواجه شد.")
        return
    await state.clear()
    await message.answer("✅ آدرس ولت با موفقیت ذخیره شد.")
    await _send_crypto_wallets_manage_panel(message, db)

@router.message(F.text == "ویرایش شماره کارت")
async def edit_payment_card_start_handler(message: Message, state: FSMContext, db: DatabaseHandler) -> None:
    current_card, _ = await db.get_payment_settings()
    shown_card = current_card or settings.ADMIN_CARD_NUMBER
    await state.set_state(AdminStates.waiting_for_card_number)
    await message.answer(
        "💳 ویرایش شماره کارت\n"
        f"شماره کارت فعلی: `{shown_card}`\n\n"
        "شماره کارت جدید را ارسال کنید.",
        parse_mode="Markdown",
    )


@router.message(AdminStates.waiting_for_card_number, F.text)
async def set_payment_card_number_handler(message: Message, state: FSMContext, db: DatabaseHandler) -> None:
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
        await db.set_payment_card_number(card_number)
    except Exception:
        logger.exception("Updating payment card number failed")
        await message.answer("❌ ذخیره شماره کارت با خطا مواجه شد.")
        return

    await state.clear()
    await message.answer(
        f"✅ شماره کارت جدید ذخیره شد:\n`{card_number}`",
        parse_mode="Markdown",
        reply_markup=build_admin_menu(),
    )


@router.message(F.text == "ویرایش نام صاحب کارت")
async def edit_card_holder_name_start_handler(message: Message, state: FSMContext, db: DatabaseHandler) -> None:
    _card_number, card_holder_name = await db.get_payment_settings()
    await state.set_state(AdminStates.waiting_for_card_holder_name)
    await message.answer(
        "👤 ویرایش نام صاحب کارت\n"
        f"نام فعلی: {card_holder_name or 'تنظیم نشده'}\n\n"
        "نام جدید را ارسال کنید.",
    )


@router.message(AdminStates.waiting_for_card_holder_name, F.text)
async def set_card_holder_name_handler(message: Message, state: FSMContext, db: DatabaseHandler) -> None:
    card_holder_name = message.text.strip()
    if len(card_holder_name) < 3:
        await message.answer("⚠️ نام صاحب کارت معتبر نیست.")
        return

    try:
        await db.set_payment_card_holder_name(card_holder_name)
    except Exception:
        logger.exception("Updating card holder name failed")
        await message.answer("❌ ذخیره نام صاحب کارت با خطا مواجه شد.")
        return

    await state.clear()
    await message.answer(
        f"✅ نام صاحب کارت ذخیره شد: {card_holder_name}",
        reply_markup=build_admin_menu(),
    )


@router.message(F.text == "🔙 بازگشت به منوی ادمین")
async def back_to_admin_menu_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("به منوی ادمین برگشتید.", reply_markup=build_admin_menu())


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
        await state.update_data(add_step="speed", add_payload=payload)
        await message.answer("سرعت سرویس را ارسال کنید (مثال: 100Mbps):")
        return

    if step == "speed":
        if not value:
            await message.answer("⚠️ سرعت نمی‌تواند خالی باشد.")
            return
        payload["speed"] = value
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
        await state.update_data(
            add_step="collect_items",
            add_payload=payload,
            collected_items=[],
            collect_index=1,
        )
        markup = build_finish_collecting_keyboard() if stock == -1 else None
        await message.answer("📥 لطفاً متن کانفیگ 1 را ارسال کنید", reply_markup=markup)
        return

    if step == "collect_items":
        if not value:
            await message.answer("⚠️ متن کانفیگ نمی‌تواند خالی باشد.")
            return
        collected_items = list(state_data.get("collected_items", []))
        collected_items.append(value)
        payload_stock = int(payload.get("stock", 0))
        next_index = len(collected_items) + 1
        await state.update_data(collected_items=collected_items, collect_index=next_index)

        if payload_stock > 0 and len(collected_items) >= payload_stock:
            try:
                await db.add_model_config_with_items(
                    model=str(model),
                    title=str(payload["title"]),
                    price=int(payload["price"]),
                    duration=str(payload["duration"]),
                    speed=str(payload["speed"]),
                    description=str(payload["description"]),
                    stock=payload_stock,
                    config_items=collected_items,
                )
            except Exception:
                logger.exception("Saving limited config batch failed for model=%s", model)
                await message.answer("❌ ثبت کانفیگ با خطا مواجه شد.")
                return
            await state.clear()
            await message.answer(
                f"✅ کانفیگ با موفقیت ثبت شد\n📦 تعداد کانفیگ‌ها: {len(collected_items)}",
            )
            await _send_admin_model_page(message, db, model=str(model), page=1)
            return

        await message.answer(
            f"✅ ثبت شد\n📥 لطفاً متن کانفیگ {next_index} را ارسال کنید",
            reply_markup=build_finish_collecting_keyboard() if payload_stock == -1 else None,
        )
        return


@router.callback_query(F.data == "admin_finish_collecting_configs")
async def admin_finish_collecting_configs_handler(
    callback: CallbackQuery,
    state: FSMContext,
    db: DatabaseHandler,
) -> None:
    await callback.answer()
    state_data = await state.get_data()
    if await state.get_state() != AdminServiceStates.adding_config_field.state:
        await callback.message.answer("⚠️ عملیات فعالی برای افزودن کانفیگ وجود ندارد.")
        return

    model = state_data.get("selected_model")
    step = state_data.get("add_step")
    payload = dict(state_data.get("add_payload", {}))
    collected_items = list(state_data.get("collected_items", []))
    if model not in {"nox_plus", "nox_multi"} or step != "collect_items":
        await callback.message.answer("⚠️ این دکمه در این مرحله قابل استفاده نیست.")
        return

    if len(collected_items) == 0:
        await callback.message.answer("⚠️ هنوز هیچ متن کانفیگی دریافت نشده است.")
        return

    final_stock = len(collected_items) if int(payload.get("stock", 0)) == -1 else int(payload.get("stock", 0))
    try:
        await db.add_model_config_with_items(
            model=str(model),
            title=str(payload["title"]),
            price=int(payload["price"]),
            duration=str(payload["duration"]),
            speed=str(payload["speed"]),
            description=str(payload["description"]),
            stock=final_stock,
            config_items=collected_items,
        )
    except Exception:
        logger.exception("Saving collected config items failed for model=%s", model)
        await callback.message.answer("❌ ثبت کانفیگ با خطا مواجه شد.")
        return

    await state.clear()
    await callback.message.answer(
        f"✅ کانفیگ با موفقیت ثبت شد\n📦 تعداد کانفیگ‌های ثبت‌شده: {len(collected_items)}"
    )
    await _send_admin_model_page(callback.message, db, model=str(model), page=1)


@router.callback_query(F.data.startswith("admin_edit_config:"))
async def admin_edit_config_handler(callback: CallbackQuery, db: DatabaseHandler, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    config_id = parse_int_callback_payload(callback.data, "admin_edit_config:")
    if config_id is None:
        await callback.message.answer("⚠️ شناسه کانفیگ نامعتبر است.")
        return
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
    if field not in {"title", "price", "duration", "speed", "description", "stock", "config_content"}:
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
    config_id = parse_int_callback_payload(callback.data, "admin_delete_config:")
    if config_id is None:
        await callback.message.answer("⚠️ شناسه کانفیگ نامعتبر است.")
        return
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
    config_id = parse_int_callback_payload(callback.data, "admin_confirm_delete:")
    if config_id is None:
        await callback.message.answer("⚠️ شناسه کانفیگ نامعتبر است.")
        return
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
    config_id = parse_int_callback_payload(callback.data, "admin_toggle_config:")
    if config_id is None:
        await callback.message.answer("⚠️ شناسه کانفیگ نامعتبر است.")
        return
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
