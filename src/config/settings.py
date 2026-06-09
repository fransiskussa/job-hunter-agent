import os
from dotenv import load_dotenv

# Load .env file if it exists (for local development)
load_dotenv()

class Settings:
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    DISCORD_WEBHOOK_URL: str = os.getenv("DISCORD_WEBHOOK_URL", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    SCRAPER_PROXY_SERVER: str = os.getenv("SCRAPER_PROXY_SERVER", "")
    SCRAPER_PROXY_USERNAME: str = os.getenv("SCRAPER_PROXY_USERNAME", "")
    SCRAPER_PROXY_PASSWORD: str = os.getenv("SCRAPER_PROXY_PASSWORD", "")
    
    # Google Sheets Integration
    GOOGLE_SHEET_ID: str = os.getenv("GOOGLE_SHEET_ID", "")
    GOOGLE_CREDENTIALS_JSON: str = os.getenv("GOOGLE_CREDENTIALS_JSON", "")
    GOOGLE_CREDENTIALS_PATH: str = os.getenv("GOOGLE_CREDENTIALS_PATH", "google_credentials.json")

    @classmethod
    def validate(cls):
        missing = []
        if not cls.SUPABASE_URL:
            missing.append("SUPABASE_URL")
        if not cls.SUPABASE_KEY:
            missing.append("SUPABASE_KEY")
        if not cls.DISCORD_WEBHOOK_URL:
            missing.append("DISCORD_WEBHOOK_URL")
        
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

settings = Settings
