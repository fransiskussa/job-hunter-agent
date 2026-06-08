import logging
import urllib.parse
from playwright.sync_api import Playwright
from src.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

class GlintsScraper(BaseScraper):
    def search(self, query: str, location: str) -> list[dict]:
        logger.info(f"Searching Glints jobs for '{query}' in '{location}'")
        raw_jobs = []
        
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
            encoded_query = urllib.parse.quote(query)
            url = f"https://glints.com/id/en/opportunities/jobs?keyword={encoded_query}"
            
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)
            
            cards = page.query_selector_all("[class*='JobCardSc__JobCardWrapper']") or page.query_selector_all("[data-testid='job-card-container']") or page.query_selector_all("a[href*='/opportunities/jobs/']")
            logger.info(f"Glints found {len(cards)} cards")
            
            for card in cards[:10]:
                try:
                    raw_data = self.extract(card)
                    if raw_data:
                        raw_jobs.append(raw_data)
                except Exception as e:
                    logger.debug(f"Glints error extracting card: {e}")
                    
        except Exception as e:
            logger.error(f"Error scraping Glints: {e}")
        finally:
            browser.close()
            
        return raw_jobs

    def extract(self, card) -> dict:
        tag_name = card.evaluate("el => el.tagName").lower()
        
        link_el = card if tag_name == "a" else card.query_selector("a[href*='/opportunities/jobs/']")
        url = ""
        if link_el:
            href = link_el.get_attribute("href")
            if href:
                if href.startswith("http"):
                    url = href
                else:
                    url = f"https://glints.com{href}"
                url = url.split("?")[0]
                
        title_el = card.query_selector("[class*='JobCardSc__JobTitle']") or card.query_selector("h2") or card.query_selector("h3")
        title = title_el.inner_text().strip() if title_el else ""
        
        company_el = card.query_selector("[class*='JobCardSc__CompanyName']") or card.query_selector("[class*='CompanyName']")
        company = company_el.inner_text().strip() if company_el else ""
        
        location_el = card.query_selector("[class*='JobCardSc__Location']") or card.query_selector("[class*='CardLocation']")
        location = location_el.inner_text().strip() if location_el else ""
        
        desc_el = card.query_selector("[class*='JobCardSc__DescriptionSnippet']") or card.query_selector("[class*='DescriptionSnippet']")
        description = desc_el.inner_text().strip() if desc_el else ""
        
        return {
            "title": title,
            "company": company,
            "location": location,
            "description": description,
            "url": url
        }

    def normalize(self, raw_data: dict) -> dict:
        if not raw_data.get("title") or not raw_data.get("url"):
            return {}
            
        desc = raw_data.get("description") or f"Job opportunity for a {raw_data.get('title')} at {raw_data.get('company')}."
        
        return {
            "source": "Glints",
            "title": raw_data["title"],
            "company": raw_data.get("company", "Unknown"),
            "location": raw_data.get("location", "Unknown"),
            "description": desc,
            "url": raw_data["url"]
        }
