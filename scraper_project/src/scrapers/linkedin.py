import logging
from playwright.sync_api import Page
from src.scrapers.base_scraper import BaseScraper, CookieExpiredException


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
            if not cookies:
                cookies = self.repository.get_platform_cookies("linkedin jobs")
                
            if not cookies:
                logger.warning("LinkedIn login cookies not found in database. Trying guest search...")
                raw_jobs = self._search_guest(page, query, location)
            else:
                try:
                    raw_jobs = self._search_direct(page, query, location)
                    if not raw_jobs:
                        logger.warning("Direct LinkedIn search returned 0 results. Trying guest search fallback...")
                        raw_jobs = self._search_guest(page, query, location)
                except Exception as direct_err:
                    logger.warning(f"Direct LinkedIn search failed ({direct_err}). Trying guest search fallback...")
                    raw_jobs = self._search_guest(page, query, location)

        except Exception as e:
            logger.error(f"Error scraping LinkedIn Jobs: {e}")
        finally:
            context.close()

        return raw_jobs

    def _search_guest(self, page: Page, query: str, location: str) -> list[dict]:
        """Scrape LinkedIn public jobs search as guest when login session is unavailable."""
        logger.info(f"Scraping LinkedIn Jobs as guest for '{query}' in '{location}'")
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        encoded_loc = urllib.parse.quote(location)
        url = f"https://www.linkedin.com/jobs/search?keywords={encoded_query}&location={encoded_loc}&f_TPR=r2592000"
        
        page.goto(url, wait_until="domcontentloaded", timeout=40000)
        page.wait_for_timeout(4000)
        
        # Remove login modals and backdrop overlays via JS to enable full scrolling and extraction
        page.evaluate("""
            const selectors = [
                'div[class*="sign-in-modal"]', 
                'div[class*="login-modal"]', 
                '.modal', 
                '.modal-overlay',
                '.contextual-sign-in-modal',
                '.contextual-sign-in-modal__overlay'
            ];
            selectors.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => el.remove());
            });
            document.body.style.overflow = 'auto';
            document.documentElement.style.overflow = 'auto';
        """)
        page.wait_for_timeout(1000)
        
        # Auto-scroll a few times to lazy-load more jobs
        self.auto_scroll(page, scroll_count=5, delay_ms=1000)
        
        cards = page.query_selector_all("ul.jobs-search__results-list li, .job-search-card, .base-card")
        logger.info(f"Guest LinkedIn found {len(cards)} job cards")
        
        raw_jobs = []
        for card in cards:
            try:
                title_el = (
                    card.query_selector(".base-search-card__title, .base-card__title, h3")
                    or card.query_selector("a.job-card-list__title")
                )
                title = title_el.inner_text().strip() if title_el else ""
                
                link_el = card.query_selector("a.base-card__full-link, a")
                href = link_el.get_attribute("href") if link_el else ""
                url_clean = ""
                if href:
                    url_clean = href.split("?")[0]
                    
                company_el = (
                    card.query_selector(".base-search-card__subtitle, .base-card__subtitle, h4")
                    or card.query_selector(".job-card-container__company-name")
                )
                company = company_el.inner_text().strip() if company_el else "Unknown"
                
                loc_el = (
                    card.query_selector(".job-search-card__location, span.job-search-card__location")
                    or card.query_selector(".job-card-container__metadata-item")
                )
                loc = loc_el.inner_text().strip() if loc_el else "Indonesia"
                
                desc_el = card.query_selector(".job-search-card__snippet, [class*='description-snippet']")
                desc = desc_el.inner_text().strip() if desc_el else ""
                
                if title and url_clean:
                    raw_jobs.append({
                        "title": title,
                        "company": company,
                        "location": loc,
                        "description": desc or f"Job opportunity for a {title} at {company} in {loc}.",
                        "url": url_clean,
                    })
            except Exception as card_err:
                logger.debug(f"Error parsing guest LinkedIn job card: {card_err}")
                
        return raw_jobs

    def _search_direct(self, page: Page, query: str, location: str) -> list[dict]:
        """Scrape LinkedIn directly when logged in."""
        logger.info(f"Scraping LinkedIn Jobs directly for '{query}' in '{location}' (logged-in)")
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        encoded_loc = urllib.parse.quote(location)
        url = f"https://www.linkedin.com/jobs/search/?keywords={encoded_query}&location={encoded_loc}&f_TPR=r7776000&sortBy=DD"
        
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        self.check_session_validity(page, "LinkedIn Jobs")
        page.wait_for_timeout(5000)
        
        # Auto-scroll to load more jobs in the sidebar
        self.auto_scroll(page, scroll_count=20, delay_ms=1000)
        
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



    def extract(self, element_or_page) -> dict:
        # Not used — extraction happens in _search_direct()
        return {}

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
