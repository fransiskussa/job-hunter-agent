import logging
import requests
from src.config.settings import settings

logger = logging.getLogger(__name__)

class DiscordNotifier:
    def __init__(self):
        settings.validate()
        self.webhook_url = settings.DISCORD_WEBHOOK_URL

    def send_report(self, matched_jobs: list[dict], matched_posts: list[dict]) -> bool:
        """Group matched jobs by source and send reports separated by platform."""
        
        # Filter out items with score = 0 (rejected by Gemini/irrelevant)
        active_jobs = [j for j in matched_jobs if j.get("score", 0) > 0]
        active_posts = [p for p in matched_posts if p.get("score", 0) > 0]

        # 1. Filter and sort by platform
        linkedin_jobs = [j for j in active_jobs if j.get("source") == "LinkedIn Jobs"]
        jobstreet_jobs = [j for j in active_jobs if j.get("source") == "JobStreet"]
        glints_jobs = [j for j in active_jobs if j.get("source") == "Glints"]
        kalibrr_jobs = [j for j in active_jobs if j.get("source") == "Kalibrr"]
        
        # Sort each list descending by score
        linkedin_jobs.sort(key=lambda x: x.get("score", 0), reverse=True)
        jobstreet_jobs.sort(key=lambda x: x.get("score", 0), reverse=True)
        glints_jobs.sort(key=lambda x: x.get("score", 0), reverse=True)
        kalibrr_jobs.sort(key=lambda x: x.get("score", 0), reverse=True)
        active_posts.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        success = True

        # Helper function to send in batches of 10
        def send_in_batches(title_prefix: str, items: list[dict], limit: int, send_func) -> bool:
            selected = items[:limit]
            batch_success = True
            for i in range(0, len(selected), 10):
                chunk = selected[i:i+10]
                part = f" (Part {i//10 + 1})" if len(selected) > 10 else ""
                batch_success &= send_func(f"{title_prefix}{part}", chunk)
            return batch_success

        # 2. Send each platform's report based on requested limits
        if linkedin_jobs:
            success &= send_in_batches("🚀 Top LinkedIn Jobs", linkedin_jobs, 20, self._send_platform_report)
        
        if active_posts:
            success &= send_in_batches("📢 Top LinkedIn Hiring Posts", active_posts, 20, self._send_posts_report)
            
        if jobstreet_jobs:
            success &= send_in_batches("💼 Top JobStreet Jobs", jobstreet_jobs, 40, self._send_platform_report)
                
        if glints_jobs:
            success &= send_in_batches("🎨 Top Glints Jobs", glints_jobs, 20, self._send_platform_report)
            
        if kalibrr_jobs:
            success &= send_in_batches("⚡ Top Kalibrr Jobs", kalibrr_jobs, 20, self._send_platform_report)
            
        return success

    def _send_platform_report(self, title: str, jobs: list[dict]) -> bool:
        embeds = []
        for idx, job in enumerate(jobs, 1):
            skills = job.get("matched_skills", [])
            skills_text = ", ".join(skills) if skills else "None"
            score = job.get("score", 0)
            
            color = 3066993 if score >= 80 else (15105570 if score >= 50 else 8421504)
            
            embeds.append({
                "title": f"{idx}. {job.get('title')}",
                "description": f"**Company:** {job.get('company', 'Unknown')}\n**Location:** {job.get('location', 'Unknown')}\n**Match Score:** {score}%",
                "url": job.get("url"),
                "color": color,
                "fields": [
                    {
                        "name": "Skills Matched",
                        "value": skills_text,
                        "inline": True
                    }
                ]
            })

        payload = {
            "content": f"**{title}**",
            "embeds": embeds
        }
        return self._send_payload(payload)

    def _send_posts_report(self, title: str, posts: list[dict]) -> bool:
        embeds = []
        for idx, post in enumerate(posts, 1):
            skills = post.get("matched_skills", [])
            skills_text = ", ".join(skills) if skills else "None"
            score = post.get("score", 0)
            
            color = 3447003  # Blue
            content_snippet = post.get("content", "")
            if len(content_snippet) > 200:
                content_snippet = content_snippet[:200] + "..."
                
            embeds.append({
                "title": f"{idx}. Post by {post.get('author_name')}",
                "description": f"**Company:** {post.get('company', 'LinkedIn Member')}\n**Content:** {content_snippet}\n**Match Score:** {score}%",
                "url": post.get("post_url"),
                "color": color,
                "fields": [
                    {
                        "name": "Skills Matched",
                        "value": skills_text,
                        "inline": True
                    }
                ]
            })

        payload = {
            "content": f"**{title}**",
            "embeds": embeds
        }
        return self._send_payload(payload)

    def _send_payload(self, payload: dict) -> bool:
        try:
            res = requests.post(self.webhook_url, json=payload, timeout=15)
            if res.status_code in [200, 204]:
                logger.info("Discord embed sent successfully.")
                return True
            else:
                logger.error(f"Failed to send Discord payload: {res.status_code} - {res.text}")
                return False
        except Exception as e:
            logger.error(f"Error sending Discord Webhook: {e}")
            return False
