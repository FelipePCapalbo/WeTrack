import os


def _parse_rate_limits(value: str):
    raw = value or ""
    parts = [p.strip() for p in raw.split(";")]
    return [p for p in parts if p]


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "your_secret_key")
    DATABASE_URL = os.environ.get(
        "DATABASE_URL",
        "postgresql://db_cdpro:admin@localhost:5432/db_cdpro",
    )
    RATE_LIMITS = _parse_rate_limits(os.environ.get("RATE_LIMITS", "200 per day;50 per hour"))
    DEBUG = os.environ.get("DEBUG", "1") == "1"
    PORT = int(os.environ.get("PORT", "5000"))


