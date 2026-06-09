import logging
from datetime import datetime
from supabase import Client

logger = logging.getLogger(__name__)

class JobRepository:
    def __init__(self, supabase: Client):
        self.supabase = supabase

    def get_user_profile(self) -> dict:
        """Fetch the first user profile from database."""
        try:
            response = self.supabase.table("user_profile").select("*").limit(1).execute()
            if response.data:
                return response.data[0]
        except Exception as e:
            logger.error(f"Error fetching user profile: {e}")
        
        # Return default if empty or error
        return {
            "skills": ["Python", "Docker", "React", "AWS", "PostgreSQL", "CI/CD", "Git", "Playwright", "FastAPI"],
            "preferred_roles": ["Backend Engineer", "Software Engineer", "Fullstack Developer"],
            "preferred_locations": ["Remote", "Jakarta", "Tangerang", "Indonesia"]
        }

    def save_jobs(self, jobs: list[dict]) -> list[dict]:
        """Save jobs to the jobs table, skipping existing URLs. Returns inserted jobs."""
        inserted_jobs = []
        for job in jobs:
            try:
                # Check if job already exists by url to avoid duplicates
                check = self.supabase.table("jobs").select("id").eq("url", job["url"]).execute()
                if check.data:
                    continue
                
                # Insert
                res = self.supabase.table("jobs").insert({
                    "source": job["source"],
                    "title": job["title"],
                    "company": job["company"],
                    "location": job["location"],
                    "description": job["description"],
                    "url": job["url"]
                }).execute()
                if res.data:
                    inserted_jobs.append(res.data[0])
            except Exception as e:
                logger.error(f"Error saving job {job.get('title')} from {job.get('source')}: {e}")
        return inserted_jobs

    def save_job_matches(self, matches: list[dict]):
        """Save match results."""
        if not matches:
            return
        try:
            self.supabase.table("job_matches").insert(matches).execute()
        except Exception as e:
            logger.error(f"Error saving job matches: {e}")

    def save_linkedin_posts(self, posts: list[dict]) -> list[dict]:
        """Save hiring posts to linkedin_posts table, skipping duplicates. Returns inserted posts."""
        inserted_posts = []
        for post in posts:
            try:
                check = self.supabase.table("linkedin_posts").select("id").eq("post_url", post["post_url"]).execute()
                if check.data:
                    continue
                
                res = self.supabase.table("linkedin_posts").insert({
                    "author_name": post.get("author_name"),
                    "author_profile_url": post.get("author_profile_url"),
                    "company": post.get("company"),
                    "content": post.get("content"),
                    "post_url": post.get("post_url")
                }).execute()
                if res.data:
                    inserted_posts.append(res.data[0])
            except Exception as e:
                logger.error(f"Error saving LinkedIn post: {e}")
        return inserted_posts

    def update_source_status(self, source_name: str, status: str):
        """Update last_scraped_at and status for a job source."""
        try:
            self.supabase.table("job_sources").upsert({
                "source_name": source_name,
                "last_scraped_at": datetime.utcnow().isoformat(),
                "status": status
            }, on_conflict="source_name").execute()
        except Exception as e:
            logger.error(f"Error updating job source status: {e}")

    def get_platform_cookies(self, platform_name: str) -> list[dict]:
        """Fetch cookies for a specific platform from the database."""
        try:
            response = self.supabase.table("platform_sessions") \
                .select("cookies") \
                .eq("platform_name", platform_name.lower()) \
                .execute()
            if response.data:
                return response.data[0].get("cookies", [])
        except Exception as e:
            logger.error(f"Error fetching cookies for {platform_name} from DB: {e}")
        return []

    def save_platform_cookies(self, platform_name: str, cookies: list[dict]):
        """Save/upsert cookies for a specific platform to the database."""
        try:
            self.supabase.table("platform_sessions").upsert({
                "platform_name": platform_name.lower(),
                "cookies": cookies,
                "updated_at": datetime.utcnow().isoformat()
            }, on_conflict="platform_name").execute()
            logger.info(f"Successfully saved/updated cookies for {platform_name} in DB.")
        except Exception as e:
            logger.error(f"Error saving cookies for {platform_name} to DB: {e}")


