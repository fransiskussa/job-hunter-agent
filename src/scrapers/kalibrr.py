from src.scrapers.base_scraper import BaseScraper, CookieExpiredException

logger = logging.getLogger(__name__)


class KalibrrScraper(BaseScraper):
    """
    Kalibrr Indonesia Scraper — optimized with auto-scroll, updated selectors,
    and retry mechanism.
    """

    def search(self, query: str, location: str) -> list[dict]:
        logger.info(f"Searching Kalibrr jobs for '{query}' in '{location}'")
        raw_jobs = []
        seen_urls = set()

        context = self._new_context("kalibrr")
        page = context.new_page()
        page.set_default_timeout(30000)

        try:
            encoded_query = urllib.parse.quote(query)
            url = f"https://www.kalibrr.com/job-board/te/{encoded_query}?country=Indonesia&sort=freshness"

            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self.check_session_validity(page, "Kalibrr")
            page.wait_for_timeout(4000)

            # Auto-scroll to load more cards
            self.auto_scroll(page, scroll_count=4, delay_ms=1500)

            # Multiple selector strategies
            cards = (
                page.query_selector_all(".k-border-b")
                or page.query_selector_all("[itemscope][itemtype='http://schema.org/JobPosting']")
                or page.query_selector_all("[class*='JobCard']")
                or page.query_selector_all("[class*='job-card']")
                or page.query_selector_all("a[href*='/c/'][href*='/jobs/']")
            )
            logger.info(f"Kalibrr found {len(cards)} cards after scroll")

            for card in cards:
                try:
                    raw_data = self.extract(card)
                    if raw_data and raw_data.get("title") and raw_data.get("url"):
                        url_clean = raw_data["url"]
                        if url_clean not in seen_urls:
                            seen_urls.add(url_clean)
                            raw_jobs.append(raw_data)
                except Exception as e:
                    logger.debug(f"Kalibrr error extracting card: {e}")

            logger.info(f"Kalibrr extracted {len(raw_jobs)} unique jobs")

            # Retry with alternative search if no results
            if not raw_jobs:
                self.random_delay(2000, 4000)
                logger.info("Kalibrr retry with alternative URL...")

                # Try direct search endpoint
                alt_url = f"https://www.kalibrr.com/job-board/te/{encoded_query}?country=Indonesia"
                page.goto(alt_url, wait_until="domcontentloaded", timeout=30000)
                self.check_session_validity(page, "Kalibrr")
                page.wait_for_timeout(4000)
                self.auto_scroll(page, scroll_count=3, delay_ms=1500)

                cards = (
                    page.query_selector_all(".k-border-b")
                    or page.query_selector_all("a[href*='/jobs/']")
                )
                logger.info(f"Kalibrr retry found {len(cards)} cards")

                for card in cards:
                    try:
                        raw_data = self.extract(card)
                        if raw_data and raw_data.get("title") and raw_data.get("url"):
                            url_clean = raw_data["url"]
                            if url_clean not in seen_urls:
                                seen_urls.add(url_clean)
                                raw_jobs.append(raw_data)
                    except Exception as e:
                        logger.debug(f"Kalibrr retry error: {e}")

        except CookieExpiredException:
            raise
        except Exception as e:
            logger.error(f"Error scraping Kalibrr: {e}")
        finally:
            context.close()

        logger.info(f"Kalibrr total: {len(raw_jobs)} jobs collected")
        return raw_jobs

    def extract(self, card) -> dict:
        title = ""
        url = ""
        company = ""
        location = ""
        description = ""

        links = card.query_selector_all("a")

        # Check if card itself is an <a> tag
        tag_name = ""
        try:
            tag_name = card.evaluate("el => el.tagName").lower()
        except Exception:
            pass
        if tag_name == "a":
            links = [card] + links

        # 1. Cari tautan pekerjaan
        for link in links:
            href = link.get_attribute("href") or ""
            text = link.inner_text().strip()

            if href and len(text) > 2:
                # Skip company-only links (except if it contains /jobs/)
                if any(x in href.lower() for x in ["/c/", "/companies/", "company"]):
                    if "/jobs/" not in href.lower():
                        continue

                title = text.split("\n")[0].strip()
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
                company = text.split("\n")[0].strip()
                break

        # Fallback: title
        if not title:
            title_el = (
                card.query_selector("[itemprop='title']")
                or card.query_selector("[class*='JobTitle']")
                or card.query_selector("[class*='job-title']")
                or card.query_selector("h2 a")
                or card.query_selector("h3 a")
                or card.query_selector("a")
            )
            title = title_el.inner_text().strip() if title_el else ""

        # Fallback: company
        if not company:
            company_el = (
                card.query_selector("[itemprop='hiringOrganization']")
                or card.query_selector("[class*='CompanyName']")
                or card.query_selector(".k-text-subdued a")
            )
            company = company_el.inner_text().strip() if company_el else ""

        # Location
        location_el = (
            card.query_selector("[itemprop='jobLocation']")
            or card.query_selector("[class*='Location']")
            or card.query_selector(".k-text-subdued")
        )
        location = location_el.inner_text().strip() if location_el else "Indonesia"

        # Description
        desc_el = (
            card.query_selector("[class*='Description']")
            or card.query_selector("[class*='teaser']")
            or card.query_selector("p")
        )
        description = desc_el.inner_text().strip() if desc_el else ""
        
        if not description:
            description = f"Job opportunity for a {title} at {company} in {location}."

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

        return {
            "source": "Kalibrr",
            "title": raw_data["title"],
            "company": raw_data.get("company", "Unknown"),
            "location": raw_data.get("location", "Indonesia"),
            "description": raw_data.get("description", ""),
            "url": raw_data["url"],
        }
