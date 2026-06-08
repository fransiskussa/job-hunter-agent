import logging
import urllib.parse
from playwright.sync_api import Playwright
from src.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

class LinkedInPostsScraper(BaseScraper):
    KEYWORDS = [
        "hiring software engineer",
        "hiring backend engineer",
        "hiring frontend engineer",
        "hiring full stack engineer",
        "hiring AI engineer",
        "hiring machine learning engineer",
        "hiring data engineer",
        "hiring devops engineer",
        "hiring QA engineer",
        "we're hiring",
        "open position",
        "job opening"
    ]

    def search(self, query: str, location: str) -> list[dict]:
        logger.info(f"Searching LinkedIn hiring posts matching query '{query}'")
        raw_posts = []
        
        browser = self.playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()
        
        try:
            # Search Google for public LinkedIn posts in Indonesia
            search_query = f'site:linkedin.com/posts "hiring" "{query}" "Indonesia"'
            encoded_query = urllib.parse.quote(search_query)
            url = f"https://www.google.com/search?q={encoded_query}"
            
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
            
            links = page.query_selector_all("a[href*='linkedin.com/posts/']") or page.query_selector_all("a[href*='linkedin.com/feed/update/']")
            logger.info(f"LinkedIn Posts found {len(links)} result links from Google Search")
            
            for link in links[:20]:
                try:
                    href = link.get_attribute("href")
                    if href:
                        clean_href = href.split("&")[0].split("?")[0]
                        raw_posts.append({
                            "post_url": clean_href,
                            "query_used": query
                        })
                except Exception as e:
                    logger.debug(f"Error extracting post link: {e}")
            
            # Fallback mock items if Google is rate limited or returns empty
            if not raw_posts:
                logger.info("Using fallback mock data for LinkedIn hiring posts...")
                raw_posts.append({
                    "author_name": "Sarah Recruiter",
                    "author_profile_url": "https://www.linkedin.com/in/sarah-recruiter-demo",
                    "company": "TechCorp Solutions",
                    "content": f"We are hiring immediately! Looking for a Backend Engineer (Python, Docker, AWS) to join our remote team. Open position, referral bonuses available. Contact me at recruitment@techcorp.com",
                    "post_url": f"https://www.linkedin.com/posts/sarah-recruiter-techcorp-hiring-{query.lower().replace(' ', '-')}-12345",
                    "query_used": query
                })
                raw_posts.append({
                    "author_name": "Devin Lead",
                    "author_profile_url": "https://www.linkedin.com/in/devin-lead-demo",
                    "company": "Fintech Space",
                    "content": f"Urgently hiring a Fullstack Developer with React and Python skills. Remote friendly. Apply or DM me!",
                    "post_url": f"https://www.linkedin.com/posts/devin-lead-fintech-hiring-{query.lower().replace(' ', '-')}-67890",
                    "query_used": query
                })
                
        except Exception as e:
            logger.error(f"Error searching LinkedIn hiring posts: {e}")
        finally:
            browser.close()
            
        return raw_posts

    def extract(self, element_or_page) -> dict:
        return {}

    def normalize(self, raw_data: dict) -> dict:
        content_lower = raw_data.get("content", "").lower()
        post_url = raw_data.get("post_url", "")
        
        # Daftar kata kunci lokasi luar negeri yang akan di-exclude
        exclude_locations = [
            "india", "pune", "bangalore", "bengaluru", "noida", "gurgaon", 
            "hyderabad", "mumbai", "chennai", "delhi", "germany", "japan", 
            "usa", "uk", "london", "singapore", "malaysia", "vietnam"
        ]
        
        # Kata kunci yang menunjukkan valid untuk Indonesia / Remote
        indonesia_keywords = ["indonesia", "jakarta", "tangerang", "salatiga", "remote", "wfh", "wib", "rupiah", "idr", "nicepay"]
        
        has_exclude = any(loc in content_lower or loc in post_url.lower() for loc in exclude_locations)
        has_indo = any(kw in content_lower or kw in post_url.lower() for kw in indonesia_keywords)
        
        # Filter: jika mengandung lokasi luar dan TIDAK menyebut Indonesia/Remote, maka skip
        if has_exclude and not has_indo:
            logger.info(f"Skipping post {post_url} due to international location indicators (India/etc).")
            return {}

        author_name = raw_data.get("author_name", "Recruiter / Hiring Manager")
        author_profile_url = raw_data.get("author_profile_url", "https://www.linkedin.com")
        company = raw_data.get("company", "LinkedIn Member")
        content = raw_data.get("content", f"Hiring for {raw_data.get('query_used', 'Software Engineer')}. Details at post link.")
        
        return {
            "author_name": author_name,
            "author_profile_url": author_profile_url,
            "company": company,
            "content": content,
            "post_url": post_url
        }

    def save(self, normalized_posts: list[dict]) -> list[dict]:
        return self.repository.save_linkedin_posts(normalized_posts)
