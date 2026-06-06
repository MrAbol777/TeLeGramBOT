from __future__ import annotations

from aiogram.types import Message

from keyboards.user_menu import build_main_menu

WELCOME_MESSAGE = """
<b><tg-emoji emoji-id='5462910521739063094'>😀</tg-emoji> سلام ، به مجموعه Nox خوش اومدی .</b>

<tg-emoji emoji-id='5210956306952758910'>👀</tg-emoji> • قابلیت های ربات مجموعه :
<tg-emoji emoji-id='5956109811136335664'>🛜</tg-emoji>• خرید سرویس
<tg-emoji emoji-id='5809695698865623554'>🖥</tg-emoji>• مشاهده اطلاعات سرویس
<tg-emoji emoji-id='5868268899480375540'>💎</tg-emoji>• شارژ موجودی
<tg-emoji emoji-id='5839449299557028781'>🎁</tg-emoji>• زیرمجموعه گیری

<tg-emoji emoji-id='5803322139197051431'>❤️</tg-emoji> یکی از دکمه های زیر رو انتخاب کن تا شروع کنیم
""".strip()


async def render_main_menu(message: Message) -> None:
    await message.answer(
        text=WELCOME_MESSAGE,
        parse_mode="HTML",
        reply_markup=build_main_menu(),
    )
