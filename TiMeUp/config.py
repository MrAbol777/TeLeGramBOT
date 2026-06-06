import os


TOKEN = os.getenv("UPTIME_BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("UPTIME_ADMIN_ID", "0"))
MAIN_BOT_USERNAME = os.getenv("UPTIME_MAIN_BOT_USERNAME", "")
LOG_FILE_PATH = os.getenv("UPTIME_LOG_FILE_PATH", "")
