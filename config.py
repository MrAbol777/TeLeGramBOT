from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_ID: int
    SUPPORT_ID: str = "@support"
    ADMIN_CARD_NUMBER: str = "شماره کارت مدیریت تنظیم نشده است"
    UPTIME_BOT_TOKEN: str = ""
    UPTIME_ADMIN_ID: int = 0
    UPTIME_MAIN_BOT_USERNAME: str = ""
    UPTIME_LOG_FILE_PATH: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )


settings = Settings()
