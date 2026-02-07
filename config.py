import os
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# Load .env
load_dotenv()


def _decrypt_(value: str | None) -> str | None:
    """
    Decrypts the value only if DECRYPTION_KEY exists.
    Allows plain-text fallback for local dev if needed.
    """
    if not value:
        return value

    key = os.getenv("DECRYPTION_KEY")
    if not key:
        # No decryption key → assume plain text (useful for local dev)
        return value

    try:
        fernet = Fernet(key.encode())
        return fernet.decrypt(value.encode()).decode()
    except Exception:
        # If decryption fails, return original value (safe fallback)
        return value


class Config:
    MONGO_URI = _decrypt_(os.getenv("MONGO_URI"))
    JWT_SECRET_KEY = _decrypt_(os.getenv("JWT_SECRET_KEY"))
    GOOGLE_API_KEY = _decrypt_(os.getenv("GOOGLE_API_KEY"))
    CORS_ORIGIN = _decrypt_(os.getenv("CORS_ORIGIN"))
    SENDER_EMAIL = _decrypt_(os.getenv("SENDER_EMAIL"))
    APP_PASSWORD = _decrypt_(os.getenv("APP_PASSWORD"))
