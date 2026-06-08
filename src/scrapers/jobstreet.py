import logging
import urllib.parse
from playwright.sync_api import Playwright
from src.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

class JobStreetScraper(BaseScraper):
    def search(self, query: str, location: str) -> list[dict]:
        logger.info(f"Searching JobStreet jobs for '{query}' in '{location}'")
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
            url = f"https://id.jobstreet.com/id/jobs?keywords={encoded_query}"
            
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)
            
            cards = page.query_selector_all("article") or page.query_selector_all("[data-testid='job-card']") or page.query_selector_all("[data-card-type='JobCard']")
            logger.info(f"JobStreet found {len(cards)} cards")
            
            for card in cards[:10]:
                try:
                    raw_data = self.extract(card)
                    if raw_data:
                        raw_jobs.append(raw_data)
                except Exception as e:
                    logger.debug(f"JobStreet error extracting card: {e}")
                    
        except Exception as e:
            logger.error(f"Error scraping JobStreet: {e}")
        finally:
            browser.close()
            
        return raw_jobs

    def extract(self, card) -> dict:
        title_el = card.query_selector("[data-testid='job-title']") or card.query_selector("a[href*='/job/']")
        title = title_el.inner_text().strip() if title_el else ""
        
        url = ""
        link_el = card.query_selector("a[href*='/job/']") or title_el
        if link_el:
            href = link_el.get_attribute("href")
            if href:
                if href.startswith("http"):
                    url = href
                else:
                    url = f"https://id.jobstreet.com{href}"
                url = url.split("?")[0]
                
        company_el = card.query_selector("[data-testid='company-name']") or card.query_selector("a[href*='/companies/']")
        company = company_el.inner_text().strip() if company_el else ""
        
        location_el = card.query_selector("[data-testid='job-location']")
        location = location_el.inner_text().strip() if location_el else ""
        
        desc_el = card.query_selector("[data-testid='job-teaser']") or card.query_selector("ul")
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
            "source": "JobStreet",
            "title": raw_data["title"],
            "company": raw_data.get("company", "Unknown"),
            "location": raw_data.get("location", "Unknown"),
            "description": desc,
            "url": raw_data["url"]
        }
