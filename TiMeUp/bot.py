import asyncio
import json
import logging
import html
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_ID, MAIN_BOT_USERNAME, TOKEN
from health_check import (
    get_deep_link_url,
    get_last_check_detail,
    health_check,
    mark_main_bot_response,
    read_last_log_error,
    set_bot_instance,
)
from keyboards.main_menu import get_main_menu

BASE_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = BASE_DIR / "settings.json"


class IntervalState(StatesGroup):
    waiting_for_interval = State()


@dataclass
class MonitorStatus:
    is_online: bool | None = None
    last_check_at: datetime | None = None
    offline_alert_sent: bool = False


status = MonitorStatus()
router = Router()
logger = logging.getLogger(__name__)


def is_admin(message: Message) -> bool:
    return bool(message.from_user and message.from_user.id == ADMIN_ID)


def load_interval() -> int:
    if not SETTINGS_PATH.exists():
        save_interval(3)
        return 3

    try:
        with SETTINGS_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        save_interval(3)
        return 3

    interval = data.get("interval", 3)
    if isinstance(interval, int) and 1 <= interval <= 60:
        return interval

    save_interval(3)
    return 3


def save_interval(interval: int) -> None:
    with SETTINGS_PATH.open("w", encoding="utf-8") as file:
        json.dump({"interval": interval}, file, ensure_ascii=False, indent=2)


def status_text() -> str:
    if status.is_online is None:
        return "نامشخص (هنوز چکی انجام نشده)"
    return "🟢 Online" if status.is_online else "🔴 Offline"


def last_check_text() -> str:
    if status.last_check_at is None:
        return "-"
    return status.last_check_at.strftime("%Y-%m-%d %H:%M:%S")


def safe_detail_text() -> str:
    return html.escape(get_last_check_detail())


def esc(text: str) -> str:
    return html.escape(text)


def deep_link_text() -> str:
    return (
        "برای تست دستی اتصال ربات اصلی، روی دکمه زیر بزنید.\n"
        f"لینک مستقیم: {get_deep_link_url()}"
    )


def deep_link_markup():
    builder = InlineKeyboardBuilder()
    builder.button(text="تست اتصال", url=get_deep_link_url())
    return builder.as_markup()


async def run_single_check(bot: Bot, notify_if_offline: bool = True) -> bool:
    online = await health_check()
    status.is_online = online
    status.last_check_at = datetime.now()
    logger.info("run_single_check: online=%s detail=%s", online, get_last_check_detail())

    if online:
        status.offline_alert_sent = False
    elif notify_if_offline and not status.offline_alert_sent:
        logger.warning("run_single_check: offline alert triggered")
        await bot.send_message(
            ADMIN_ID,
            "⚠️ هشدار: ربات اصلی در آخرین بررسی Offline تشخیص داده شد.",
        )
        status.offline_alert_sent = True

    return online


async def scheduler_loop(bot: Bot) -> None:
    await asyncio.sleep(2)
    while True:
        try:
            await run_single_check(bot, notify_if_offline=True)
        except Exception as exc:
            logger.exception("scheduler_loop: health check failed: %s", exc)
        interval = load_interval()
        await asyncio.sleep(interval * 60)


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    if not is_admin(message):
        return

    interval = load_interval()
    await message.answer(
        html.escape(
            "✅ پنل Uptime Bot آماده است.\n"
            f"بازه فعلی چک: {interval} دقیقه\n"
            f"وضعیت: {status_text()}"
        ),
        parse_mode="HTML",
        reply_markup=get_main_menu(),
    )


@router.message(F.text == "وضعیت فعلی")
async def current_status_handler(message: Message) -> None:
    if not is_admin(message):
        return

    interval = load_interval()
    text = html.escape(
        f"وضعیت فعلی: {status_text()}\n"
        f"آخرین چک: {last_check_text()}\n"
        f"بازه چک: {interval} دقیقه\n"
        f"جزئیات: {get_last_check_detail()}"
    )
    if status.is_online is False:
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=deep_link_markup(),
        )
        return

    await message.answer(text, parse_mode="HTML")


@router.message(F.text == "چک کردن الان")
async def check_now_handler(message: Message) -> None:
    if not is_admin(message):
        return

    await message.answer(html.escape("در حال بررسی..."), parse_mode="HTML")
    online = await run_single_check(message.bot, notify_if_offline=True)
    result_text = html.escape(
        f"نتیجه بررسی: {'🟢 Online' if online else '🔴 Offline'}\n"
        f"زمان: {last_check_text()}\n"
        f"جزئیات: {get_last_check_detail()}"
    )
    if not online:
        await message.answer(
            result_text,
            parse_mode="HTML",
            reply_markup=deep_link_markup(),
        )
        return

    await message.answer(result_text, parse_mode="HTML")


@router.message(F.text == "تست آنلاین بودن (Deep Link)")
async def deep_link_test_handler(message: Message) -> None:
    if not is_admin(message):
        return

    await message.answer(
        html.escape(deep_link_text()),
        parse_mode="HTML",
        reply_markup=deep_link_markup(),
    )


@router.message(F.chat.type == "private")
async def main_bot_reply_handler(message: Message) -> None:
    if not MAIN_BOT_USERNAME:
        return

    expected_username = MAIN_BOT_USERNAME.lstrip("@").casefold()
    sender_username = (message.from_user.username or "").casefold() if message.from_user else ""
    if sender_username != expected_username:
        return

    mark_main_bot_response()


@router.message(F.text == "آخرین خطا")
async def last_error_handler(message: Message) -> None:
    if not is_admin(message):
        return

    last_error = read_last_log_error()
    await message.answer(
        html.escape(f"آخرین خطا:\n{last_error}"),
        parse_mode="HTML",
    )


@router.message(F.text == "تنظیم فاصله زمانی")
async def set_interval_prompt_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(message):
        return

    await state.set_state(IntervalState.waiting_for_interval)
    await message.answer(
        html.escape("یک عدد بین 1 تا 60 (دقیقه) ارسال کنید:"),
        parse_mode="HTML",
    )


@router.message(IntervalState.waiting_for_interval)
async def set_interval_value_handler(message: Message, state: FSMContext) -> None:
    if not is_admin(message):
        await state.clear()
        return

    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer(
            html.escape("❌ فقط عدد صحیح بفرستید (1 تا 60)."),
            parse_mode="HTML",
        )
        return

    interval = int(text)
    if not 1 <= interval <= 60:
        await message.answer(
            html.escape("❌ عدد باید بین 1 تا 60 باشد."),
            parse_mode="HTML",
        )
        return

    save_interval(interval)
    await state.clear()
    await message.answer(
        html.escape(f"✅ فاصله زمانی روی {interval} دقیقه تنظیم شد."),
        parse_mode="HTML",
    )


@router.message()
async def ignore_non_admin(message: Message) -> None:
    if not is_admin(message):
        return


async def main() -> None:
    if not TOKEN:
        raise ValueError("TOKEN در config.py خالی است. لطفاً مقداردهی کنید.")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    bot = Bot(
        token=TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    set_bot_instance(bot)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    scheduler_task = asyncio.create_task(scheduler_loop(bot))
    try:
        await dp.start_polling(bot)
    finally:
        scheduler_task.cancel()
        with __import__("contextlib").suppress(asyncio.CancelledError):
            await scheduler_task
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
