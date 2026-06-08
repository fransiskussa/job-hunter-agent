import logging
import requests
from src.config.settings import settings

logger = logging.getLogger(__name__)

class DiscordNotifier:
    def __init__(self):
        settings.validate()
        self.webhook_url = settings.DISCORD_WEBHOOK_URL

    def send_report(self, matched_jobs: list[dict], matched_posts: list[dict]) -> bool:
        """Send daily reports of Jobs and Hiring Posts as Discord Embeds."""
        success_jobs = self._send_jobs_report(matched_jobs)
        success_posts = self._send_posts_report(matched_posts)
        return success_jobs and success_posts

    def _send_jobs_report(self, matched_jobs: list[dict]) -> bool:
        if not matched_jobs:
            logger.info("No matched jobs to send.")
            return True
            
        embeds = []
        for idx, job in enumerate(matched_jobs[:10], 1):
            skills = job.get("matched_skills", [])
            skills_text = ", ".join(skills) if skills else "None"
            score = job.get("score", 0)
            
            color = 3066993 if score >= 80 else (15105570 if score >= 50 else 8421504)
            
            embeds.append({
                "title": f"{idx}. {job.get('title')}",
                "description": f"**Company:** {job.get('company')}\n**Location:** {job.get('location')}\n**Match Score:** {score}%",
                "url": job.get("url"),
                "color": color,
                "fields": [
                    {
                        "name": "Source",
                        "value": job.get("source", "Jobs"),
                        "inline": True
                    },
                    {
                        "name": "Skills Matched",
                        "value": skills_text,
                        "inline": True
                    }
                ]
            })

        payload = {
            "content": "🚀 **Daily Job Report: Top 10 Matched Jobs**",
            "embeds": embeds
        }
        return self._send_payload(payload)

    def _send_posts_report(self, matched_posts: list[dict]) -> bool:
        if not matched_posts:
            logger.info("No matched hiring posts to send.")
            return True
            
        embeds = []
        for idx, post in enumerate(matched_posts[:10], 1):
            skills = post.get("matched_skills", [])
            skills_text = ", ".join(skills) if skills else "None"
            score = post.get("score", 0)
            
            color = 3447003  # Blue for LinkedIn posts
            
            content_snippet = post.get("content", "")
            if len(content_snippet) > 200:
                content_snippet = content_snippet[:200] + "..."
                
            embeds.append({
                "title": f"{idx}. Post by {post.get('author_name')}",
                "description": f"**Company:** {post.get('company')}\n**Content:** {content_snippet}\n**Match Score:** {score}%",
                "url": post.get("post_url"),
                "color": color,
                "fields": [
                    {
                        "name": "Source",
                        "value": "LinkedIn Posts",
                        "inline": True
                    },
                    {
                        "name": "Skills Matched",
                        "value": skills_text,
                        "inline": True
                    }
                ]
            })

        payload = {
            "content": "📢 **Daily Job Report: Top 10 LinkedIn Hiring Posts**",
            "embeds": embeds
        }
        return self._send_payload(payload)

    def _send_payload(self, payload: dict) -> bool:
        try:
            res = requests.post(self.webhook_url, json=payload, timeout=10)
            if res.status_code in [200, 204]:
                logger.info("Discord embed sent successfully.")
                return True
            else:
                logger.error(f"Failed to send Discord payload: {res.status_code} - {res.text}")
                return False
        except Exception as e:
            logger.error(f"Error sending Discord Webhook: {e}")
            return False
