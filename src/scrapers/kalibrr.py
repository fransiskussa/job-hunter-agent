import logging
import urllib.parse
from playwright.sync_api import Playwright
from src.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

class KalibrrScraper(BaseScraper):
    def search(self, query: str, location: str) -> list[dict]:
        logger.info(f"Searching Kalibrr jobs for '{query}' in '{location}'")
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
        page.set_default_timeout(25000)
        
        try:
            encoded_query = urllib.parse.quote(query)
            url = f"https://www.kalibrr.com/job-board/te/{encoded_query}?country=Indonesia&sort=freshness"
            
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(6000)
            
            cards = page.query_selector_all(".k-border-b") or page.query_selector_all("[itemscope][itemtype='http://schema.org/JobPosting']") or page.query_selector_all("a[href*='/jobs/']")
            logger.info(f"Kalibrr found {len(cards)} cards")
            
            for card in cards[:10]:
                try:
                    raw_data = self.extract(card)
                    if raw_data and raw_data.get("title") and raw_data.get("url"):
                        raw_jobs.append(raw_data)
                except Exception as e:
                    logger.debug(f"Kalibrr error extracting card: {e}")
                    
        except Exception as e:
            logger.error(f"Error scraping Kalibrr: {e}")
        finally:
            browser.close()
            
        return raw_jobs

    def extract(self, card) -> dict:
        title = ""
        url = ""
        company = ""
        location = ""
        description = ""

        links = card.query_selector_all("a")

        # 1. Cari tautan pekerjaan pertama yang tidak mengarah ke organisasi
        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()
            
            if href and len(text) > 2:
                # Lewati profil organisasi
                if any(x in href.lower() for x in ["/c/", "/companies/", "company"]):
                    # Kadang link job Kalibrr berisi /c/company/jobs/123, tapi pastikan ada /jobs/
                    if "/jobs/" not in href.lower():
                        continue
                
                title = text.split("\n")[0]
                if href.startswith("http"):
                    url = href
                else:
                    url = f"https://www.kalibrr.com{href}"
                url = url.split("?")[0]
                break

        # 2. Cari Nama Perusahaan
        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()
            if "/c/" in href.lower() and "/jobs/" not in href.lower() and len(text) > 1:
                company = text
                break

        # Fallback jika title kosong
        if not title:
            title_el = card.query_selector("[itemprop='title']") or card.query_selector("h2 a") or card.query_selector("a")
            title = title_el.inner_text().strip() if title_el else ""

        # Fallback jika company kosong
        if not company:
            company_el = card.query_selector("[itemprop='hiringOrganization']") or card.query_selector(".k-text-subdued a")
            company = company_el.inner_text().strip() if company_el else ""

        location_el = card.query_selector("[itemprop='jobLocation']") or card.query_selector(".k-text-subdued")
        location = location_el.inner_text().strip() if location_el else "Indonesia"

        description = f"Job opportunity for a {title} at {company} in {location}."

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
            
        return {
            "source": "Kalibrr",
            "title": raw_data["title"],
            "company": raw_data.get("company", "Unknown"),
            "location": raw_data.get("location", "Unknown"),
            "description": raw_data.get("description", ""),
            "url": raw_data["url"]
        }
