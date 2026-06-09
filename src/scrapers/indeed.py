import logging
import urllib.parse
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
        raw_jobs = []
        context = self._new_context("indeed")
        page = context.new_page()
        page.set_default_timeout(25000)

        try:
            # Try direct Indeed search first
            try:
                raw_jobs = self._search_direct(page, query, location)
                if raw_jobs:
                    logger.info(f"✅ Successfully collected {len(raw_jobs)} jobs directly from Indeed")
                    return raw_jobs
                else:
                    logger.warning("Direct Indeed search returned 0 results. Falling back to Google Search Proxy...")
            except Exception as direct_err:
                logger.warning(f"Direct Indeed search failed ({direct_err}). Falling back to Google Search Proxy...")

            # --- FALLBACK: GOOGLE SEARCH PROXY ---
            logger.info(f"Searching Indeed jobs for '{query}' in '{location}' via Google Search Proxy")
            results = google_search_jobs(
                page=page,
                site_domain="id.indeed.com/viewjob",
                query=query,
                location=location,
                max_results=15,
            )
            self.check_session_validity(page, "Indeed")
            
            logger.info(f"[INDEED-STAGE-EXTRACT] Found {len(results)} raw Google results.")
            
            for result in results:
                raw_data = self.extract(result)
                if raw_data and raw_data.get("title") and raw_data.get("url"):
                    combined_text = f"{raw_data['title']} {raw_data.get('snippet', '')} {raw_data.get('company', '')}"
                    if is_indonesia_relevant(combined_text, raw_data["url"]):
                        raw_jobs.append(raw_data)
                    else:
                        logger.warning(f"[INDEED-STAGE-EXTRACT] Filtered out (Not Indonesia): '{raw_data['title']}' | URL: {raw_data['url']}")
                else:
                    logger.warning(f"[INDEED-STAGE-EXTRACT] Dropped result due to missing title or url: {result}")

            logger.info(f"[INDEED-STAGE-EXTRACT] {len(raw_jobs)} items passed extraction and location filters.")

            # Retry with broader query if no results
            if not raw_jobs:
                logger.warning("[INDEED-STAGE-FALLBACK] ⚠️ No results from primary Indeed search. Triggering SAFE FALLBACK MODE...")
                self.random_delay(1000, 3000)
                broader_results = google_search_jobs(
                    page=page,
                    site_domain="id.indeed.com",
                    query=query,
                    location="", # Remove location constraint
                    max_results=15,
                    extra_terms='"lowongan" OR "hiring"',
                )
                self.check_session_validity(page, "Indeed")
                logger.info(f"[INDEED-STAGE-FALLBACK] Found {len(broader_results)} raw results.")
                
                for result in broader_results:
                    raw_data = self.extract(result)
                    if raw_data and raw_data.get("title") and raw_data.get("url"):
                        combined_text = f"{raw_data['title']} {raw_data.get('snippet', '')} {raw_data.get('company', '')}"
                        if is_indonesia_relevant(combined_text, raw_data["url"]):
                            raw_jobs.append(raw_data)
                        else:
                            logger.warning(f"[INDEED-STAGE-FALLBACK] Filtered out (Not Indonesia): '{raw_data['title']}' | URL: {raw_data['url']}")
                    else:
                        logger.warning(f"[INDEED-STAGE-FALLBACK] Dropped result due to missing title or url: {result}")

                logger.info(f"[INDEED-STAGE-FALLBACK] {len(raw_jobs)} items passed fallback extraction.")

        except Exception as e:
            logger.error(f"[INDEED-STAGE-SEARCH] Error scraping Indeed: {e}")
        finally:
            context.close()

        return raw_jobs

    def _search_direct(self, page: Page, query: str, location: str) -> list[dict]:
        """Scrape Indeed directly using public search page."""
        logger.info(f"Direct Indeed search for '{query}' in '{location}'")
        import urllib.parse
        encoded_query = urllib.parse.quote(query)
        encoded_loc = urllib.parse.quote(location)
        url = f"https://id.indeed.com/jobs?q={encoded_query}&l={encoded_loc}&from=searchOnDesktopSerp&sortBy=date"
        
        page.goto(url, wait_until="domcontentloaded", timeout=40000)
        page.wait_for_timeout(4000)
        
        # Remove any popup login modals via JS
        page.evaluate("""
            const selectors = [
                'div[class*="sign-in-modal"]', 
                'div[class*="login-modal"]', 
                '.modal', 
                '.modal-overlay',
                '#credential_picker_container',
                'iframe[title*="Sign in"]'
            ];
            selectors.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => el.remove());
            });
        """)
        
        # Find card containers
        cards = page.query_selector_all("li.css-1ac2h1w, div.job_seen_beacon, td.resultContent")
        logger.info(f"Direct Indeed found {len(cards)} card elements")
        
        raw_jobs = []
        seen_urls = set()
        
        for card in cards:
            try:
                title_el = card.query_selector("a.jcs-JobTitle, h2.jobTitle a, span[id*='jobTitle'] a")
                if not title_el:
                    continue
                title = title_el.inner_text().strip()
                
                href = title_el.get_attribute("href")
                if not href:
                    continue
                
                # Extract jk key from URL to format clean URL
                jk = ""
                if "jk=" in href:
                    parsed_url = urllib.parse.urlparse(href)
                    query_params = urllib.parse.parse_qs(parsed_url.query)
                    jk_list = query_params.get("jk", query_params.get("vjk", []))
                    if jk_list:
                        jk = jk_list[0]
                
                if not jk:
                    # Try to search jk via regex
                    import re
                    match = re.search(r'[?&](?:v?)jk=([0-9a-fA-F]+)', href)
                    if match:
                        jk = match.group(1)
                        
                if jk:
                    url_clean = f"https://id.indeed.com/viewjob?jk={jk}"
                else:
                    if href.startswith("http"):
                        url_clean = href.split("?")[0]
                    else:
                        url_clean = f"https://id.indeed.com{href}".split("?")[0]
                
                if url_clean in seen_urls:
                    continue
                seen_urls.add(url_clean)
                
                company_el = card.query_selector("span[data-testid='company-name'], .companyName, [class*='company-name']")
                company = company_el.inner_text().strip() if company_el else "Unknown"
                
                loc_el = card.query_selector("div[data-testid='text-location'], .companyLocation, [class*='location']")
                loc = loc_el.inner_text().strip() if loc_el else "Indonesia"
                
                desc_el = card.query_selector("div.job-snippet, [class*='snippet']")
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
                logger.debug(f"Error parsing direct Indeed card: {card_err}")
                
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
            logger.warning(f"[INDEED-STAGE-NORMALIZE] Failed: Missing Title or URL -> {raw_data}")
            return {}

        url = raw_data.get("url", "").lower()
        
        # Reject ANY relative link (Google UI navigation buttons like /search, /travel)
        if url.startswith("/"):
            logger.warning(f"[INDEED-STAGE-NORMALIZE] Rejected Google UI relative link: '{raw_data.get('title')}' -> {url}")
            return {}
            
        # Reject non-http links just in case
        if not url.startswith("http"):
            return {}
        
        # Safe extraction of Indeed vjk to construct clean URL
        try:
            parsed_url = urllib.parse.urlparse(url)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            vjk = query_params.get("vjk", query_params.get("jk", []))
            if vjk:
                url = f"https://id.indeed.com/viewjob?jk={vjk[0]}"
        except Exception as e:
            logger.debug(f"[INDEED-STAGE-NORMALIZE] Error parsing Indeed URL query params: {e}")

        # Final check to ensure it's actually an indeed domain
        if "indeed.com" not in url or "google.com" in url:
            logger.warning(f"[INDEED-STAGE-NORMALIZE] Rejected invalid or Google UI URL: '{raw_data.get('title')}' -> {url}")
            return {}

        desc = raw_data.get("description") or f"Job opportunity for a {raw_data['title']} at {raw_data.get('company', 'Unknown')} in {raw_data.get('location', 'Indonesia')}."

        return {
            "source": "Indeed",
            "title": raw_data["title"],
            "company": raw_data.get("company", "Unknown"),
            "location": raw_data.get("location", "Indonesia"),
            "description": desc,
            "url": url,
        }
