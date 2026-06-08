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
        page.set_default_timeout(25000)
        
        try:
            encoded_query = urllib.parse.quote(query)
            # Menggunakan parameter 'where' yang benar untuk JobStreet/SEEK
            url = f"https://id.jobstreet.com/id/jobs?keywords={encoded_query}&where=Indonesia&daterange=3"
            
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(6000)
            
            cards = page.query_selector_all("article") or page.query_selector_all("[data-testid='job-card']")
            logger.info(f"JobStreet found {len(cards)} cards")
            
            for card in cards[:20]:
                try:
                    raw_data = self.extract(card)
                    if raw_data and raw_data.get("title") and raw_data.get("url"):
                        raw_jobs.append(raw_data)
                except Exception as e:
                    logger.debug(f"JobStreet error extracting card: {e}")
                    
        except Exception as e:
            logger.error(f"Error scraping JobStreet: {e}")
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
        
        # 1. Cari tautan pekerjaan utama (link pertama yang bukan profil perusahaan)
        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()
            
            if href and len(text) > 2:
                # Lewati jika link menunjuk ke organisasi/perusahaan
                if any(x in href.lower() for x in ["/companies/", "/organizations/", "company"]):
                    continue
                
                # Teks link pertama yang valid adalah judul pekerjaan
                title = text.split("\n")[0]
                if href.startswith("http"):
                    url = href
                else:
                    url = f"https://id.jobstreet.com{href}"
                url = url.split("?")[0]
                break

        # 2. Cari Nama Perusahaan
        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()
            if any(x in href.lower() for x in ["/companies/", "/organizations/", "company"]) and len(text) > 1:
                company = text
                break

        # Fallback jika title kosong
        if not title:
            title_el = card.query_selector("[data-testid='job-title']") or card.query_selector("h1") or card.query_selector("h3")
            title = title_el.inner_text().strip() if title_el else ""

        # Fallback jika company kosong
        if not company:
            company_el = card.query_selector("[data-testid='company-name']") or card.query_selector("[data-testid='job-company']")
            company = company_el.inner_text().strip() if company_el else ""

        location_el = card.query_selector("[data-testid='job-location']")
        location = location_el.inner_text().strip() if location_el else "Indonesia"

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
