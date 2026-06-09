from src.scrapers.base_scraper import BaseScraper, CookieExpiredException
from src.scrapers.google_search_proxy import google_search_jobs, is_indonesia_relevant

logger = logging.getLogger(__name__)


class IndeedScraper(BaseScraper):
    """
    Indeed Scraper via Google Search Proxy.
    
    Scraping langsung ke id.indeed.com selalu di-block oleh anti-bot.
    Strategi: gunakan Google `site:id.indeed.com` untuk menemukan listing.
    """

    def search(self, query: str, location: str) -> list[dict]:
        logger.info(f"Searching Indeed jobs for '{query}' in '{location}' via Google")
        raw_jobs = []

        context = self._new_context("indeed")
        page = context.new_page()
        page.set_default_timeout(25000)

        try:
            # Search Google for Indeed Indonesia listings
            results = google_search_jobs(
                page=page,
                site_domain="id.indeed.com",
                query=query,
                location=location,
                max_results=15,
            )
            self.check_session_validity(page, "Indeed")
            
            for result in results:
                raw_data = self.extract(result)
                if raw_data and raw_data.get("title") and raw_data.get("url"):
                    # Filter: pastikan relevan Indonesia
                    combined_text = f"{raw_data['title']} {raw_data.get('snippet', '')} {raw_data.get('company', '')}"
                    if is_indonesia_relevant(combined_text, raw_data["url"]):
                        raw_jobs.append(raw_data)
                    else:
                        logger.debug(f"Filtered out non-Indonesia Indeed result: {raw_data['title']}")

            logger.info(f"Indeed found {len(raw_jobs)} valid jobs via Google Search")

            # Retry with broader query if no results
            if not raw_jobs:
                self.random_delay(1000, 3000)
                broader_results = google_search_jobs(
                    page=page,
                    site_domain="id.indeed.com",
                    query=query,
                    location="Jakarta",
                    max_results=15,
                    extra_terms='"lowongan" OR "hiring"',
                )
                self.check_session_validity(page, "Indeed")
                for result in broader_results:
                    raw_data = self.extract(result)
                    if raw_data and raw_data.get("title") and raw_data.get("url"):
                        combined_text = f"{raw_data['title']} {raw_data.get('snippet', '')} {raw_data.get('company', '')}"
                        if is_indonesia_relevant(combined_text, raw_data["url"]):
                            raw_jobs.append(raw_data)

                logger.info(f"Indeed retry found {len(raw_jobs)} valid jobs")

        except CookieExpiredException:
            raise
        except Exception as e:
            logger.error(f"Error scraping Indeed via Google: {e}")
        finally:
            context.close()

        return raw_jobs

    def extract(self, google_result: dict) -> dict:
        """Extract job data from a Google search result dict."""
        title = google_result.get("title", "")
        url = google_result.get("url", "")
        snippet = google_result.get("snippet", "")
        company = google_result.get("company", "")

        # Clean title: remove "- Indeed" suffix, platform names
        for suffix in [" - Indeed", " | Indeed", " - Indeed.com", " | Indeed Indonesia"]:
            if title.endswith(suffix):
                title = title[: -len(suffix)].strip()

        # Try to split "Job Title - Company" pattern from title
        if not company and " - " in title:
            parts = title.rsplit(" - ", 1)
            if len(parts) == 2 and len(parts[1]) > 2:
                title = parts[0].strip()
                company = parts[1].strip()

        # Extract location hints from snippet
        location = "Indonesia"
        for loc in ["Jakarta", "Tangerang", "Bandung", "Surabaya", "Remote", "Yogyakarta", 
                     "Semarang", "Medan", "Bekasi", "Depok", "Bogor", "Malang", "Bali"]:
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
            "source": "Indeed",
            "title": raw_data["title"],
            "company": raw_data.get("company", "Unknown"),
            "location": raw_data.get("location", "Indonesia"),
            "description": desc,
            "url": raw_data["url"],
        }
