from supabase import create_client, Client
from src.config.settings import settings

def get_supabase_client() -> Client:
    settings.validate()
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
