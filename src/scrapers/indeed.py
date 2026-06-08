import logging
import urllib.parse
from playwright.sync_api import Playwright
from src.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

class IndeedScraper(BaseScraper):
    def search(self, query: str, location: str) -> list[dict]:
        logger.info(f"Searching Indeed jobs for '{query}' in '{location}'")
        raw_jobs = []
        
        browser = self.playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ],
            ignore_default_args=["--enable-automation"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            timezone_id="Asia/Jakarta"
        )
        page = context.new_page()
        page.set_default_timeout(25000)
        
        try:
            encoded_query = urllib.parse.quote(query)
            # Stripped l=Indonesia as it is redundant on id.indeed.com and might trigger detection
            url = f"https://id.indeed.com/jobs?q={encoded_query}&fromage=3"
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(6000) # Tunggu 6 detik agar render dinamis selesai
            
            cards = page.query_selector_all(".result") or page.query_selector_all("[class*='job_seen_beacon']") or page.query_selector_all("td.resultContent")
            logger.info(f"Indeed found {len(cards)} cards")
            
            if len(cards) == 0:
                page_title = page.title()
                content = page.content().lower()
                logger.warning(f"Indeed page loaded but found 0 cards. Page title: '{page_title}'")
                if "cloudflare" in content or "verify you are human" in content or "just a moment" in content:
                    logger.warning("Indeed block detected: Cloudflare challenge page active.")
            
            for card in cards:
                try:
                    raw_data = self.extract(card)
                    if raw_data and raw_data.get("title") and raw_data.get("url"):
                        raw_jobs.append(raw_data)
                except Exception as e:
                    logger.debug(f"Indeed error extracting card: {e}")
                    
        except Exception as e:
            logger.error(f"Error scraping Indeed: {e}")
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
        
        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()
            
            # Cari link pekerjaan Indeed (biasanya /rc/clk atau /pagead/clk atau /viewjob atau /jobs)
            is_job_link = any(p in href.lower() for p in ["/rc/clk", "/pagead/clk", "/viewjob", "/jobs/view/"])
            if is_job_link and len(text) > 3:
                title = text
                if href.startswith("http"):
                    url = href
                else:
                    url = f"https://id.indeed.com{href}"
                url = url.split("?")[0]
                break

        # Fallback jika title kosong
        if not title:
            title_el = card.query_selector("h2.jobTitle") or card.query_selector("a[id*='job_']")
            title = title_el.inner_text().strip() if title_el else ""

        # Cari Nama Perusahaan
        company_el = card.query_selector("[data-testid='company-name']") or card.query_selector(".companyName") or card.query_selector("span.companyName")
        company = company_el.inner_text().strip() if company_el else ""

        # Lokasi
        location_el = card.query_selector("[data-testid='text-location']") or card.query_selector(".companyLocation")
        location = location_el.inner_text().strip() if location_el else "Indonesia"

        salary_el = card.query_selector("[class*='salary-snippet']") or card.query_selector("[class*='metadataContainer']")
        salary = salary_el.inner_text().strip() if salary_el else None

        desc_el = card.query_selector("div.job-snippet") or card.query_selector("table.jobCard_mainContent")
        description = desc_el.inner_text().strip() if desc_el else ""

        return {
            "title": title,
            "company": company,
            "location": location,
            "salary": salary,
            "description": description,
            "url": url
        }

    def normalize(self, raw_data: dict) -> dict:
        if not raw_data.get("title") or not raw_data.get("url"):
            return {}
            
        desc = raw_data.get("description") or f"Job opportunity for a {raw_data.get('title')} at {raw_data.get('company')} in {raw_data.get('location')}."
        if raw_data.get("salary"):
            desc = f"Salary: {raw_data['salary']}\n\n{desc}"
            
        return {
            "source": "Indeed",
            "title": raw_data["title"],
            "company": raw_data.get("company", "Unknown"),
            "location": raw_data.get("location", "Unknown"),
            "description": desc,
            "url": raw_data["url"]
        }
