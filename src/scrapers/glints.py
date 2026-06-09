import logging
import urllib.parse
from src.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class GlintsScraper(BaseScraper):
    """
    Glints Indonesia Scraper — optimized with auto-scroll, robust selectors,
    and retry mechanism.
    """

    def search(self, query: str, location: str) -> list[dict]:
        logger.info(f"Searching Glints jobs for '{query}' in '{location}'")
        raw_jobs = []
        seen_urls = set()

        context = self._new_context("glints")
        page = context.new_page()
        page.set_default_timeout(30000)

        try:
            encoded_query = urllib.parse.quote(query)
            url = f"https://glints.com/id/en/opportunities/jobs?keyword={encoded_query}&country=ID&sortBy=LATEST"

            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)

            # Auto-scroll to load more cards (Glints uses infinite scroll)
            self.auto_scroll(page, scroll_count=5, delay_ms=1500)

            # Try multiple card selectors
            cards = (
                page.query_selector_all("[class*='JobCardSc__JobCardWrapper']")
                or page.query_selector_all("[data-testid='job-card-container']")
                or page.query_selector_all("[class*='CompactJobCard']")
                or page.query_selector_all("[class*='job-card']")
                or page.query_selector_all("a[href*='/opportunities/jobs/']")
            )
            logger.info(f"Glints found {len(cards)} cards after scroll")

            for card in cards:
                try:
                    raw_data = self.extract(card)
                    if raw_data and raw_data.get("title") and raw_data.get("url"):
                        url_clean = raw_data["url"]
                        if url_clean not in seen_urls:
                            seen_urls.add(url_clean)
                            raw_jobs.append(raw_data)
                except Exception as e:
                    logger.debug(f"Glints error extracting card: {e}")

            logger.info(f"Glints extracted {len(raw_jobs)} unique jobs")

            # Retry with broader search if no results
            if not raw_jobs:
                self.random_delay(2000, 4000)
                logger.info("Glints retry with broader search...")
                
                # Try alternative URL format
                alt_url = f"https://glints.com/id/en/opportunities/jobs?keyword={encoded_query}&country=ID&lowestLocationLevel=COUNTRY"
                page.goto(alt_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(4000)
                self.auto_scroll(page, scroll_count=3, delay_ms=1500)

                cards = (
                    page.query_selector_all("[class*='JobCardSc__JobCardWrapper']")
                    or page.query_selector_all("a[href*='/opportunities/jobs/']")
                )
                logger.info(f"Glints retry found {len(cards)} cards")

                for card in cards:
                    try:
                        raw_data = self.extract(card)
                        if raw_data and raw_data.get("title") and raw_data.get("url"):
                            url_clean = raw_data["url"]
                            if url_clean not in seen_urls:
                                seen_urls.add(url_clean)
                                raw_jobs.append(raw_data)
                    except Exception as e:
                        logger.debug(f"Glints retry error: {e}")

        except Exception as e:
            logger.error(f"Error scraping Glints: {e}")
        finally:
            context.close()

        logger.info(f"Glints total: {len(raw_jobs)} jobs collected")
        return raw_jobs

    def extract(self, card) -> dict:
        title = ""
        url = ""
        company = ""
        location = ""
        description = ""
        salary = ""

        # Check if the card itself is an <a> tag
        tag_name = ""
        try:
            tag_name = card.evaluate("el => el.tagName").lower()
        except Exception:
            pass

        links = card.query_selector_all("a")
        if tag_name == "a":
            links = [card] + links

        # 1. Cari tautan pekerjaan utama
        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()

            if href and len(text) > 2:
                if any(x in href.lower() for x in ["/organizations/", "/companies/", "company"]):
                    continue

                title = text.split("\n")[0].strip()
                if href.startswith("http"):
                    url = href
                else:
                    url = f"https://glints.com{href}"
                url = url.split("?")[0]
                break

        # 2. Cari Nama Perusahaan
        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()
            if any(x in href.lower() for x in ["/organizations/", "company"]) and len(text) > 1:
                company = text.split("\n")[0].strip()
                break

        # Fallback: title
        if not title:
            title_el = (
                card.query_selector("[class*='JobTitle']")
                or card.query_selector("[class*='jobTitle']")
                or card.query_selector("[class*='job-title']")
                or card.query_selector("h2")
                or card.query_selector("h3")
            )
            title = title_el.inner_text().strip() if title_el else ""

        # Fallback: company
        if not company:
            company_el = (
                card.query_selector("[class*='CompanyName']")
                or card.query_selector("[class*='companyName']")
                or card.query_selector("[class*='company-name']")
            )
            company = company_el.inner_text().strip() if company_el else ""

        # Location
        location_el = (
            card.query_selector("[class*='Location']")
            or card.query_selector("[class*='location']")
            or card.query_selector("[class*='CardLocation']")
        )
        location = location_el.inner_text().strip() if location_el else "Indonesia"

        # Salary
        salary_el = (
            card.query_selector("[class*='Salary']")
            or card.query_selector("[class*='salary']")
        )
        salary = salary_el.inner_text().strip() if salary_el else ""

        # Description
        desc_el = (
            card.query_selector("[class*='DescriptionSnippet']")
            or card.query_selector("[class*='description']")
            or card.query_selector("p")
        )
        description = desc_el.inner_text().strip() if desc_el else ""
        
        if salary and salary not in description:
            description = f"💰 {salary}\n{description}"

        return {
            "title": title,
            "company": company,
            "location": location,
            "description": description,
            "url": url,
        }

    def normalize(self, raw_data: dict) -> dict:
        if not raw_data.get("title") or not raw_data.get("url"):
            return {}

        desc = raw_data.get("description") or f"Job opportunity for a {raw_data['title']} at {raw_data.get('company', 'Unknown')}."

        return {
            "source": "Glints",
            "title": raw_data["title"],
            "company": raw_data.get("company", "Unknown"),
            "location": raw_data.get("location", "Indonesia"),
            "description": desc,
            "url": raw_data["url"],
        }
