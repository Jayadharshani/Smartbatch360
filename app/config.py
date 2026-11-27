import os
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///smartbatch.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    VARIANCE_TOLERANCE = Decimal(os.getenv("VARIANCE_TOLERANCE", "3"))  # percent
    COMPANY_NAME = os.getenv("COMPANY_NAME", "Sri Murugan Snacks Pvt Ltd")
    COMPANY_GSTIN = os.getenv("COMPANY_GSTIN", "33ABCDE1234F1Z5")
    COMPANY_STATE = os.getenv("COMPANY_STATE", "Tamil Nadu")
    COMPANY_ADDRESS = os.getenv("COMPANY_ADDRESS", "Industrial Estate, Tiruchirappalli, Tamil Nadu")


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
