from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from database.db_handler import DatabaseHandler
from keyboards.user_menu import build_main_menu

logger = logging.getLogger(__name__)
router = Router(name="start")
REFERRAL_REWARD_AMOUNT = 2000

WELCOME_MESSAGE = """
<b><tg-emoji emoji-id='5462910521739063094'>😀</tg-emoji> سلام ، به مجموعه Nox خوش اومدی .</b>

<tg-emoji emoji-id='5210956306952758910'>👀</tg-emoji> • قابلیت های ربات مجموعه :
<tg-emoji emoji-id='5956109811136335664'>🛜</tg-emoji>• خرید سرویس
<tg-emoji emoji-id='5809695698865623554'>🖥</tg-emoji>• مشاهده اطلاعات سرویس
<tg-emoji emoji-id='5868268899480375540'>💎</tg-emoji>• شارژ موجودی
<tg-emoji emoji-id='5839449299557028781'>🎁</tg-emoji>• زیرمجموعه گیری
<tg-emoji emoji-id='5875008300168254524'>📫</tg-emoji>• ثبت درخواست نمایندگی

<tg-emoji emoji-id='5803322139197051431'>❤️</tg-emoji> یکی از دکمه های زیر رو انتخاب کن تا شروع کنیم
""".strip()


@router.message(CommandStart())
async def start_handler(message: Message, db: DatabaseHandler, bot: Bot) -> None:
    if message.from_user is None:
        return

    user_id = message.from_user.id
    referral_id: int | None = None
    start_parts = (message.text or "").strip().split(maxsplit=1)
    if len(start_parts) > 1 and start_parts[1].isdigit():
        parsed_ref_id = int(start_parts[1])
        if parsed_ref_id != user_id:
            referral_id = parsed_ref_id

    try:
        user_exists = await db.user_exists(user_id)
        if not user_exists:
            await db.add_user_with_referrer(user_id, referral_id)
            if referral_id is not None:
                await db.add_balance(referral_id, REFERRAL_REWARD_AMOUNT)
                await bot.send_message(
                    referral_id,
                    "تبریک! یک کاربر جدید با لینک شما عضو شد و ۲۰۰۰ تومان هدیه گرفتید.",
                )
        else:
            await db.add_user_if_not_exists(user_id)
    except Exception:
        logger.exception("Database operation failed in /start for user_id=%s", user_id)
        await message.answer("خطایی در ثبت اطلاعات رخ داد. لطفاً دوباره تلاش کنید.")
        return

    await message.answer(
        text=WELCOME_MESSAGE,
        parse_mode="HTML",
        reply_markup=build_main_menu(),
    )
