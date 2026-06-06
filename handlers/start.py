from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from database.db_handler import DatabaseHandler
from keyboards.user_menu import build_main_menu

logger = logging.getLogger(__name__)
router = Router(name="start")

WELCOME_MESSAGE = """
<b><tg-emoji emoji-id='5462910521739063094'>😀</tg-emoji> سلام ، به مجموعه Nox خوش اومدی .</b>

<tg-emoji emoji-id='5210956306952758910'>👀</tg-emoji> • قابلیت های ربات مجموعه :
<tg-emoji emoji-id='5956109811136335664'>🛜</tg-emoji>• خرید سرویس
<tg-emoji emoji-id='5809695698865623554'>🖥</tg-emoji>• مشاهده اطلاعات سرویس
<tg-emoji emoji-id='5868268899480375540'>💎</tg-emoji>• شارژ موجودی
<tg-emoji emoji-id='5839449299557028781'>🎁</tg-emoji>• زیرمجموعه گیری

<tg-emoji emoji-id='5803322139197051431'>❤️</tg-emoji> یکی از دکمه های زیر رو انتخاب کن تا شروع کنیم
""".strip()


async def send_main_menu(message: Message) -> None:
    await message.answer(
        text=WELCOME_MESSAGE,
        parse_mode="HTML",
        reply_markup=build_main_menu(),
    )


async def handle_start_entry(
    message: Message,
    db: DatabaseHandler,
    bot: Bot,
    *,
    start_text: str | None = None,
) -> None:
    if message.from_user is None:
        return

    user_id = message.from_user.id
    referral_id: int | None = None
    parsed_text = start_text if start_text is not None else (message.text or "")
    start_parts = parsed_text.strip().split(maxsplit=1)
    if len(start_parts) > 1 and start_parts[1].isdigit():
        parsed_ref_id = int(start_parts[1])
        if parsed_ref_id != user_id:
            referral_id = parsed_ref_id

    try:
        reward_raw = await db.get_setting("referral_reward_amount", "2000")
        try:
            referral_reward_amount = max(0, int(str(reward_raw or "2000")))
        except ValueError:
            referral_reward_amount = 2000

        user_exists = await db.user_exists(user_id)
        if not user_exists:
            await db.add_user_with_referrer(user_id, referral_id)
            if referral_id is not None:
                await db.add_balance(referral_id, referral_reward_amount)
                await bot.send_message(
                    referral_id,
                    (
                        "تبریک! یک کاربر جدید با لینک شما عضو شد و "
                        f"{referral_reward_amount:,} تومان هدیه گرفتید."
                    ).replace(",", "٬"),
                )
        else:
            await db.add_user_if_not_exists(user_id)
    except Exception:
        logger.exception("Database operation failed in /start for user_id=%s", user_id)
        await message.answer("خطایی در ثبت اطلاعات رخ داد. لطفاً دوباره تلاش کنید.")
        return

    await send_main_menu(message)


@router.message(CommandStart())
async def start_handler(message: Message, db: DatabaseHandler, bot: Bot) -> None:
    await handle_start_entry(message, db, bot, start_text=message.text)
