import os
import json
import logging
from src.database.supabase_client import get_supabase_client
from src.database.repository import JobRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("UploadCookies")

def upload_all_cookies():
    cookies_dir = "cookies"
    if not os.path.exists(cookies_dir):
        logger.warning(f"Directory '{cookies_dir}' does not exist. Please create it and add your JSON cookie files.")
        return

    supabase_client = get_supabase_client()
    repo = JobRepository(supabase_client)

    uploaded_count = 0
    for filename in os.listdir(cookies_dir):
        if filename.endswith(".json"):
            platform_name = os.path.splitext(filename)[0]
            # Replace underscores/hyphens with spaces for user-friendliness, or keep as is
            # We standardize on lowercase and underscore mapping, but we can store it directly
            file_path = os.path.join(cookies_dir, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    cookies_data = json.load(f)
                
                # Validation: must be list of dicts
                if not isinstance(cookies_data, list):
                    logger.warning(f"Skipping {filename}: cookies data must be a list of cookie objects.")
                    continue
                
                logger.info(f"Uploading cookies for platform '{platform_name}' ({len(cookies_data)} cookies)...")
                repo.save_platform_cookies(platform_name, cookies_data)
                uploaded_count += 1
            except Exception as e:
                logger.error(f"Error uploading {filename}: {e}")

    logger.info(f"Done! Successfully uploaded {uploaded_count} platform sessions to Supabase.")

if __name__ == "__main__":
    upload_all_cookies()
