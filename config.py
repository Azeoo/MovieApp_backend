import os
from dotenv import load_dotenv
load_dotenv(override=True)

class Config:
    MONGO_URI = os.getenv("MONGO_URI")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    CORS_ORIGIN = os.getenv("CORS_ORIGIN")
    SENDER_EMAIL = os.getenv("SENDER_EMAIL")
    APP_PASSWORD = os.getenv("APP_PASSWORD")

