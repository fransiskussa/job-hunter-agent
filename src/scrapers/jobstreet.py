import logging
import urllib.parse
from src.scrapers.base_scraper import BaseScraper, CookieExpiredException

logger = logging.getLogger(__name__)


class JobStreetScraper(BaseScraper):
    """
    JobStreet Indonesia Scraper — optimized with auto-scroll, pagination,
    and robust selector fallbacks.
    """

    MAX_PAGES = 3  # Scrape up to 3 pages

    def search(self, query: str, location: str) -> list[dict]:
        logger.info(f"Searching JobStreet jobs for '{query}' in '{location}'")
        raw_jobs = []
        seen_urls = set()

        context = self._new_context("jobstreet")
        page = context.new_page()
        page.set_default_timeout(30000)

        try:
            for page_num in range(1, self.MAX_PAGES + 1):
                encoded_query = urllib.parse.quote(query)
                # JobStreet/SEEK Indonesia URL with pagination
                url = f"https://id.jobstreet.com/id/jobs?keywords={encoded_query}&where=Indonesia&daterange=3&page={page_num}"

                logger.info(f"JobStreet page {page_num}: {url}")
                
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    self.check_session_validity(page, "JobStreet")
                    page.wait_for_timeout(4000)  # Wait for initial render

                    # Auto-scroll to trigger lazy-loading
                    self.auto_scroll(page, scroll_count=4, delay_ms=1200)

                    # Try multiple card selectors (JobStreet/SEEK changes these)
                    cards = (
                        page.query_selector_all("article[data-testid='job-card']")
                        or page.query_selector_all("article")
                        or page.query_selector_all("[data-testid='job-card']")
                        or page.query_selector_all("[data-search-sol-meta]")
                        or page.query_selector_all("div[data-job-id]")
                    )
                    logger.info(f"JobStreet page {page_num} found {len(cards)} cards")

                    if not cards:
                        logger.info(f"JobStreet page {page_num}: no cards found, stopping pagination")
                        break

                    page_count = 0
                    for card in cards:
                        try:
                            raw_data = self.extract(card)
                            if raw_data and raw_data.get("title") and raw_data.get("url"):
                                url_clean = raw_data["url"]
                                if url_clean not in seen_urls:
                                    seen_urls.add(url_clean)
                                    raw_jobs.append(raw_data)
                                    page_count += 1
                        except Exception as e:
                            logger.debug(f"JobStreet error extracting card: {e}")

                    logger.info(f"JobStreet page {page_num}: extracted {page_count} new jobs")

                    # If very few results on this page, no point continuing
                    if page_count < 3:
                        break

                except CookieExpiredException:
                    raise
                except Exception as e:
                    logger.error(f"Error loading JobStreet page {page_num}: {e}")
                    break

                # Random delay between pages
                if page_num < self.MAX_PAGES:
                    self.random_delay(1500, 3000)

        except CookieExpiredException:
            raise
        except Exception as e:
            logger.error(f"Error scraping JobStreet: {e}")
        finally:
            context.close()

        logger.info(f"JobStreet total: {len(raw_jobs)} jobs collected")
        return raw_jobs

    def extract(self, card) -> dict:
        title = ""
        url = ""
        company = ""
        location = ""
        description = ""
        salary = ""

        links = card.query_selector_all("a")

        # 1. Cari tautan pekerjaan utama
        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()

            if href and len(text) > 2:
                # Skip company/organization links
                if any(x in href.lower() for x in ["/companies/", "/organizations/", "company"]):
                    continue

                # Text pertama yang valid = judul pekerjaan
                title = text.split("\n")[0].strip()
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
                company = text.split("\n")[0].strip()
                break

        # Fallback: title via data-testid / heading
        if not title:
            title_el = (
                card.query_selector("[data-testid='job-title']")
                or card.query_selector("[data-testid='job-card-title']")
                or card.query_selector("h1")
                or card.query_selector("h2")
                or card.query_selector("h3")
            )
            title = title_el.inner_text().strip() if title_el else ""

        # Fallback: company via data-testid
        if not company:
            company_el = (
                card.query_selector("[data-testid='company-name']")
                or card.query_selector("[data-testid='job-company']")
                or card.query_selector("[data-testid='job-card-company']")
            )
            company = company_el.inner_text().strip() if company_el else ""

        # Location
        location_el = (
            card.query_selector("[data-testid='job-location']")
            or card.query_selector("[data-testid='job-card-location']")
        )
        location = location_el.inner_text().strip() if location_el else "Indonesia"

        # Salary (bonus info)
        salary_el = (
            card.query_selector("[data-testid='job-salary']")
            or card.query_selector("[data-testid='job-card-salary']")
        )
        salary = salary_el.inner_text().strip() if salary_el else ""

        # Description/teaser
        desc_el = (
            card.query_selector("[data-testid='job-teaser']")
            or card.query_selector("[data-testid='job-card-teaser']")
            or card.query_selector("ul")
        )
        description = desc_el.inner_text().strip() if desc_el else ""
        
        # Add salary to description if available
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
            "source": "JobStreet",
            "title": raw_data["title"],
            "company": raw_data.get("company", "Unknown"),
            "location": raw_data.get("location", "Indonesia"),
            "description": desc,
            "url": raw_data["url"],
        }
