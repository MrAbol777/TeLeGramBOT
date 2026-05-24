import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
MAIN_BOT_PATH = ROOT_DIR / "bot.py"
UPTIME_BOT_PATH = ROOT_DIR / "TiMeUp" / "bot.py"


def run() -> None:
    if not MAIN_BOT_PATH.exists():
        raise FileNotFoundError(f"Main bot not found: {MAIN_BOT_PATH}")
    if not UPTIME_BOT_PATH.exists():
        raise FileNotFoundError(f"Uptime bot not found: {UPTIME_BOT_PATH}")

    processes = [
        subprocess.Popen([sys.executable, str(MAIN_BOT_PATH)], cwd=ROOT_DIR),
        subprocess.Popen([sys.executable, str(UPTIME_BOT_PATH)], cwd=ROOT_DIR / "TiMeUp"),
    ]

    def shutdown(*_: object) -> None:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        while True:
            for process in processes:
                return_code = process.poll()
                if return_code is not None:
                    shutdown()
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    run()
