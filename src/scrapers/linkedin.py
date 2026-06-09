import logging
from playwright.sync_api import Page
from src.scrapers.base_scraper import BaseScraper, CookieExpiredException
from src.scrapers.google_search_proxy import google_search_jobs, is_indonesia_relevant

logger = logging.getLogger(__name__)


class LinkedInScraper(BaseScraper):
    """
    LinkedIn Jobs Scraper via Google Search Proxy.
    
    LinkedIn public jobs page menggunakan lazy-loading dan selector yang sering berubah.
    Strategi: gunakan Google `site:linkedin.com/jobs/view` untuk hasil lebih stabil.
    """

    def search(self, query: str, location: str) -> list[dict]:
        context = self._new_context("linkedin")
        page = context.new_page()
        page.set_default_timeout(30000)

        raw_jobs = []
        try:
            # Check if we have cookies in database
            cookies = self.repository.get_platform_cookies("linkedin")
            if cookies:
                try:
                    raw_jobs = self._search_direct(page, query, location)
                    if raw_jobs:
                        logger.info(f"✅ Successfully collected {len(raw_jobs)} jobs directly from LinkedIn")
                        return raw_jobs
                except Exception as direct_err:
                    logger.warning(f"Direct LinkedIn scraping failed: {direct_err}. Falling back to Google Search Proxy.")

            # --- FALLBACK: GOOGLE SEARCH PROXY ---
            logger.info(f"Searching LinkedIn jobs for '{query}' in '{location}' via Google Search Proxy")
            results = google_search_jobs(
                page=page,
                site_domain="linkedin.com/jobs/view",
                query=query,
                location=location,
                max_results=15,
            )
            self.check_session_validity(page, "LinkedIn Jobs")
            
            for result in results:
                raw_data = self.extract(result)
                if raw_data and raw_data.get("title") and raw_data.get("url"):
                    combined_text = f"{raw_data['title']} {raw_data.get('snippet', '')} {raw_data.get('company', '')}"
                    if is_indonesia_relevant(combined_text, raw_data["url"]):
                        raw_jobs.append(raw_data)
                    else:
                        logger.debug(f"Filtered out non-Indonesia LinkedIn result: {raw_data['title']}")

            logger.info(f"LinkedIn Jobs found {len(raw_jobs)} valid jobs via Google Search")

            # Retry with different search if no results
            if not raw_jobs:
                self.random_delay(1000, 3000)
                broader_results = google_search_jobs(
                    page=page,
                    site_domain="linkedin.com/jobs",
                    query=query,
                    location="Jakarta",
                    max_results=15,
                    extra_terms='"hiring" OR "engineer" OR "developer"',
                )
                self.check_session_validity(page, "LinkedIn Jobs")
                for result in broader_results:
                    raw_data = self.extract(result)
                    if raw_data and raw_data.get("title") and raw_data.get("url"):
                        combined_text = f"{raw_data['title']} {raw_data.get('snippet', '')} {raw_data.get('company', '')}"
                        if is_indonesia_relevant(combined_text, raw_data["url"]):
                            raw_jobs.append(raw_data)

                logger.info(f"LinkedIn Jobs retry found {len(raw_jobs)} valid jobs")

        except CookieExpiredException:
            raise
        except Exception as e:
            logger.error(f"Error scraping LinkedIn Jobs: {e}")
        finally:
            context.close()

        return raw_jobs

    def _search_direct(self, page: Page, query: str, location: str) -> list[dict]:
        """Scrape LinkedIn directly when logged in."""
        logger.info(f"Scraping LinkedIn Jobs directly for '{query}' in '{location}' (logged-in)")
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        encoded_loc = urllib.parse.quote(location)
        url = f"https://www.linkedin.com/jobs/search/?keywords={encoded_query}&location={encoded_loc}"
        
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        self.check_session_validity(page, "LinkedIn Jobs")
        page.wait_for_timeout(5000)
        
        # Auto-scroll to load more jobs in the sidebar
        self.auto_scroll(page, scroll_count=3, delay_ms=1000)
        
        cards = (
            page.query_selector_all("li.jobs-search-results__list-item")
            or page.query_selector_all("[data-occludable-job-id]")
            or page.query_selector_all(".job-card-container")
            or page.query_selector_all(".jobs-search-two-pane__job-card-container")
        )
        
        logger.info(f"Direct LinkedIn found {len(cards)} job cards")
        raw_jobs = []
        for card in cards:
            try:
                # Extract details
                title_el = card.query_selector("a.job-card-list__title, .job-card-list__title, a.job-card-container__link, [class*='job-card-list__title']")
                title = title_el.inner_text().strip() if title_el else ""
                
                href = title_el.get_attribute("href") if title_el else ""
                url_clean = ""
                if href:
                    if href.startswith("http"):
                        url_clean = href.split("?")[0]
                    else:
                        url_clean = f"https://www.linkedin.com{href}".split("?")[0]
                
                company_el = card.query_selector(".job-card-container__company-name, .job-card-list__company-name, [class*='company-name']")
                company = company_el.inner_text().strip() if company_el else ""
                
                loc_el = card.query_selector(".job-card-container__metadata-item, .job-card-list__metadata-item, [class*='metadata-item']")
                loc = loc_el.inner_text().strip() if loc_el else "Indonesia"
                
                desc_el = card.query_selector(".job-card-list__description-snippet, [class*='description-snippet']")
                desc = desc_el.inner_text().strip() if desc_el else ""
                
                if title and url_clean:
                    raw_jobs.append({
                        "title": title,
                        "company": company,
                        "location": loc,
                        "description": desc or f"Job listing for {title} at {company}",
                        "url": url_clean,
                    })
            except Exception as card_err:
                logger.debug(f"Error parsing direct LinkedIn job card: {card_err}")
                
        return raw_jobs

    def extract(self, google_result: dict) -> dict:
        """Extract job data from a Google search result dict."""
        title = google_result.get("title", "")
        url = google_result.get("url", "")
        snippet = google_result.get("snippet", "")
        company = google_result.get("company", "")

        # Clean title: remove LinkedIn suffixes
        for suffix in [" | LinkedIn", " - LinkedIn", " on LinkedIn"]:
            if suffix.lower() in title.lower():
                idx = title.lower().index(suffix.lower())
                title = title[:idx].strip()

        # Try to extract "Job Title - Company" from title
        if not company and " - " in title:
            parts = title.rsplit(" - ", 1)
            if len(parts) == 2 and len(parts[1]) > 2:
                title = parts[0].strip()
                company = parts[1].strip()

        # Try to extract "Company hiring Title" pattern
        if not company:
            lower_title = title.lower()
            if " hiring " in lower_title:
                idx = lower_title.index(" hiring ")
                company = title[:idx].strip()
                title = title[idx + 8:].strip()

        # Extract location from snippet
        location = "Indonesia"
        for loc in ["Jakarta", "Tangerang", "Bandung", "Surabaya", "Remote", "Yogyakarta", 
                     "Semarang", "Medan", "Bekasi", "Depok", "Bogor", "Malang", "Bali",
                     "Indonesia", "Serpong", "BSD"]:
            if loc.lower() in snippet.lower() or loc.lower() in title.lower():
                location = loc
                break

        # Clean URL
        if url:
            url = url.split("?")[0]

        return {
            "title": title,
            "company": company,
            "location": location,
            "description": snippet,
            "url": url,
            "snippet": snippet,
        }

    def normalize(self, raw_data: dict) -> dict:
        if not raw_data.get("title") or not raw_data.get("url"):
            return {}

        desc = raw_data.get("description") or f"Job opportunity for a {raw_data['title']} at {raw_data.get('company', 'Unknown')} in {raw_data.get('location', 'Indonesia')}."

        return {
            "source": "LinkedIn Jobs",
            "title": raw_data["title"],
            "company": raw_data.get("company", "Unknown"),
            "location": raw_data.get("location", "Indonesia"),
            "description": desc,
            "url": raw_data["url"],
        }
