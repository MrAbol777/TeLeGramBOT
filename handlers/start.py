from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from database.db_handler import DatabaseHandler
from keyboards.start_menu import build_start_menu

logger = logging.getLogger(__name__)
router = Router(name="start")

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
async def start_handler(message: Message, db: DatabaseHandler) -> None:
    if message.from_user is None:
        return

    user_id = message.from_user.id

    try:
        if not await db.user_exists(user_id):
            await db.add_user(user_id)
    except Exception:
        logger.exception("Database operation failed in /start for user_id=%s", user_id)
        await message.answer("خطایی در ثبت اطلاعات رخ داد. لطفاً دوباره تلاش کنید.")
        return

    await message.answer(
        text=WELCOME_MESSAGE,
        parse_mode="HTML",
        reply_markup=build_start_menu(),
    )
