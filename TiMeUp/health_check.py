import logging
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from datetime import datetime
from pathlib import Path

from aiogram import Bot

from config import LOG_FILE_PATH

_bot: Bot | None = None
_last_check_detail: str = "هنوز بررسی انجام نشده است."
DEEP_LINK_URL = "https://t.me/NoxStarBot?start"
logger = logging.getLogger(__name__)


def set_bot_instance(bot: Bot) -> None:
    global _bot
    _bot = bot


def mark_main_bot_response() -> None:
    return None


def get_last_check_detail() -> str:
    return _last_check_detail


def get_deep_link_url() -> str:
    return DEEP_LINK_URL


def _log_file_freshness_detail(max_age_seconds: int = 300) -> tuple[bool, str]:
    log_path = Path(LOG_FILE_PATH)
    if not log_path.exists():
        return False, f"فایل لاگ پیدا نشد: {log_path}"

    try:
        last_modified = datetime.fromtimestamp(log_path.stat().st_mtime)
    except OSError as exc:
        return False, f"عدم دسترسی به زمان تغییر لاگ: {exc}"

    age_seconds = (datetime.now() - last_modified).total_seconds()
    if age_seconds <= max_age_seconds:
        return True, f"لاگ تازه است (age:{int(age_seconds)}s, threshold:{max_age_seconds}s)"
    return False, f"لاگ قدیمی است (age:{int(age_seconds)}s, threshold:{max_age_seconds}s)"


def _probe_deep_link(timeout_seconds: float = 6.0) -> tuple[bool, str]:
    request = Request(
        DEEP_LINK_URL,
        method="GET",
        headers={
            "User-Agent": "TiMeUpHealthCheck/1.0",
        },
    )
    started_at = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            status_code = getattr(response, "status", None) or response.getcode()
            if 200 <= status_code < 400:
                return True, f"Deep Link reachable (status:{status_code}, latency:{elapsed_ms}ms)"
            return False, f"Deep Link bad status (status:{status_code}, latency:{elapsed_ms}ms)"
    except HTTPError as exc:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        return False, f"Deep Link HTTP error (status:{exc.code}, latency:{elapsed_ms}ms)"
    except URLError as exc:
        reason = getattr(exc, "reason", str(exc))
        return False, f"Deep Link network error: {reason}"
    except TimeoutError:
        return False, f"Deep Link timeout after {timeout_seconds}s"
    except Exception as exc:
        return False, f"Deep Link unexpected error: {exc}"


async def health_check() -> bool:
    global _last_check_detail

    if _bot is None:
        raise RuntimeError("Bot instance is not configured for health_check.")

    deep_link_ok, deep_link_detail = await __import__("asyncio").to_thread(
        _probe_deep_link, 6.0
    )
    is_fresh, freshness_detail = _log_file_freshness_detail(max_age_seconds=300)

    if deep_link_ok:
        _last_check_detail = f"🟢 آنلاین | {deep_link_detail} | {freshness_detail}"
        logger.info("health_check: %s", _last_check_detail)
        return True

    _last_check_detail = f"🔴 آفلاین | {deep_link_detail} | {freshness_detail} | لینک دستی: {DEEP_LINK_URL}"
    logger.warning("health_check: %s", _last_check_detail)
    return False


def read_last_log_error() -> str:
    log_path = Path(LOG_FILE_PATH)
    if not log_path.exists():
        return "فایل لاگ پیدا نشد."

    error_pattern = re.compile(r"(error|exception)", re.IGNORECASE)

    try:
        with log_path.open("r", encoding="utf-8", errors="ignore") as file:
            lines = file.readlines()
    except Exception as exc:
        return f"خواندن لاگ با خطا مواجه شد: {exc}"

    for line in reversed(lines):
        if error_pattern.search(line):
            return line.strip() or "خطای خالی ثبت شده است."

    return "هیچ ERROR/EXCEPTION در لاگ پیدا نشد."
