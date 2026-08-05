import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    """
    Central configuration object for the KapuLetu Backend.
    Loads environment variables from the system (in Production) or a .env file (in Development).
    """
    # PostgreSQL connection string (e.g. postgresql://user:pass@host:port/db)
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    
    # Amazon QLDB Ledger name for immutable records
    QLDB_LEDGER_NAME: str = os.getenv("QLDB_LEDGER_NAME", "kapuletu-ledger")
    
    # Meta WhatsApp Cloud API Webhook Verification Token
    META_VERIFY_TOKEN: str = os.getenv("META_VERIFY_TOKEN", "")
    
    # Meta WhatsApp Cloud API credentials for sending messages
    META_ACCESS_TOKEN: str = os.getenv("META_ACCESS_TOKEN", "")
    META_PHONE_NUMBER_ID: str = os.getenv("META_PHONE_NUMBER_ID", "")
    
    # Africa's Talking Credentials
    AT_USERNAME: str = os.getenv("AT_USERNAME", "sandbox")
    AT_API_KEY: str = os.getenv("AT_API_KEY", "")
    AT_SENDER_ID: str = os.getenv("AT_SENDER_ID", "")
    
    # JWT Secret Key for signing custom tokens
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "your-super-secret-local-dev-key")
    
    # Frontend URL for generating public links
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "https://app.kapuletu.co.ke")

def get_config() -> Config:
    """
    Returns a fresh instance of the configuration.
    Using a dataclass ensures type-safety and easy attribute access.
    """
    return Config()
