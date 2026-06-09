import logging
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
        logger.info(f"Searching LinkedIn jobs for '{query}' in '{location}' via Google")
        raw_jobs = []

        context = self._new_context("linkedin")
        page = context.new_page()
        page.set_default_timeout(25000)

        try:
            # Search Google for LinkedIn job listings in Indonesia
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
            logger.error(f"Error scraping LinkedIn Jobs via Google: {e}")
        finally:
            context.close()

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
