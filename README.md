# ربات تلگرام فروشگاهی (aiogram 3.x)

این پروژه یک ساختار حرفه‌ای و ماژولار برای توسعه ربات فروشگاهی تلگرام با **Python 3.12+** و **aiogram 3.x** است.

## ویژگی‌ها (فاز ۱)

- ساختار ماژولار و تمیز
- مدیریت تنظیمات با `.env` و `pydantic-settings`
- دیتابیس Async با `aiosqlite`
- ثبت خودکار کاربر در اولین `/start`
- پیام خوش‌آمدگویی HTML با Custom Emoji
- منوی شیشه‌ای (Inline Keyboard) با `custom_emoji_id`

## ساختار پروژه

```text
telegramBOT/
├─ bot.py
├─ config.py
├─ .env
├─ README.md
├─ database/
│  ├─ __init__.py
│  └─ db_handler.py
├─ handlers/
│  ├─ __init__.py
│  └─ start.py
└─ keyboards/
   ├─ __init__.py
   └─ start_menu.py
```

## پیش‌نیازها

- Python 3.12 یا بالاتر
- Bot Token از BotFather
- (اختیاری) Telegram Premium برای Owner جهت استفاده کامل از Custom Emoji

## نصب و اجرا

### 1) ساخت محیط مجازی و نصب وابستگی‌ها

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install aiogram aiosqlite pydantic-settings
```

### 2) تنظیم فایل `.env`

فایل `.env` را به شکل زیر تنظیم کنید:

```env
BOT_TOKEN=PASTE_YOUR_BOT_TOKEN_HERE
ADMIN_ID=123456789
```

### 3) اجرای ربات

```bash
python3 bot.py
```

## دیتابیس

در فاز ۱ جدول `users` ساخته می‌شود:

- `user_id` (کلید اصلی)
- `balance` (پیش‌فرض 0)
- `joined_date` (زمان عضویت به فرمت ISO)

## نکات مهم

- فایل `.env` در `.gitignore` قرار دارد و نباید در گیت پوش شود.
- در `handlers/start.py` متن خوش‌آمدگویی با تگ `<tg-emoji>` تنظیم شده است.
- در `keyboards/start_menu.py` برای هر دکمه `custom_emoji_id` تعریف شده است.

## فازهای بعدی پیشنهادی

- پنل ادمین
- مدیریت محصولات و سفارش‌ها
- کیف پول/تراکنش‌ها
- سیستم تیکت و پشتیبانی
- لاگ‌گیری حرفه‌ای و هندلر خطاهای سراسری

---

ساخته شده برای توسعه سریع، قابل نگهداری و Production-Ready.
