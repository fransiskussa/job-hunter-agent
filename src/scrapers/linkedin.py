import logging
import urllib.parse
from playwright.sync_api import Playwright
from src.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

class LinkedInScraper(BaseScraper):
    def search(self, query: str, location: str) -> list[dict]:
        logger.info(f"Searching LinkedIn jobs for '{query}' in '{location}'")
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
        page.set_default_timeout(20000)
        
        try:
            encoded_query = urllib.parse.quote(query)
            encoded_location = urllib.parse.quote(location)
            url = f"https://www.linkedin.com/jobs/search?keywords={encoded_query}&location={encoded_location}&f_TPR=r86400"
            
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(2000)
            
            cards = page.query_selector_all(".jobs-search__results-list li") or page.query_selector_all(".base-card")
            logger.info(f"LinkedIn found {len(cards)} cards")
            
            for card in cards:
                try:
                    raw_data = self.extract(card)
                    if raw_data and raw_data.get("title") and raw_data.get("url"):
                        raw_jobs.append(raw_data)
                except Exception as e:
                    logger.debug(f"LinkedIn error extracting card: {e}")
                    
        except Exception as e:
            logger.error(f"Error scraping LinkedIn: {e}")
        finally:
            browser.close()
            
        return raw_jobs

    def extract(self, card) -> dict:
        title_el = card.query_selector(".base-search-card__title") or card.query_selector("h3")
        title = title_el.inner_text().strip() if title_el else ""
        
        company_el = card.query_selector(".base-search-card__subtitle") or card.query_selector("h4")
        company = company_el.inner_text().strip() if company_el else ""
        
        location_el = card.query_selector(".job-search-card__location") or card.query_selector(".job-result-card__location")
        location = location_el.inner_text().strip() if location_el else ""
        
        link_el = card.query_selector("a.base-card__full-link") or card.query_selector("a")
        url = link_el.get_attribute("href") if link_el else ""
        if url:
            url = url.split("?")[0]
            
        desc_el = card.query_selector(".job-search-card__snippet")
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
            
        desc = raw_data.get("description") or f"Job opportunity for a {raw_data.get('title')} at {raw_data.get('company')} in {raw_data.get('location')}."
        
        return {
            "source": "LinkedIn Jobs",
            "title": raw_data["title"],
            "company": raw_data.get("company", "Unknown"),
            "location": raw_data.get("location", "Unknown"),
            "description": desc,
            "url": raw_data["url"]
        }
