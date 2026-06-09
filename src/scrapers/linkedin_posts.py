import logging
import urllib.parse
import time
from src.scrapers.base_scraper import BaseScraper, CookieExpiredException
from src.scrapers.google_search_proxy import is_indonesia_relevant, EXCLUDE_LOCATIONS, INDONESIA_KEYWORDS, google_search_lock

logger = logging.getLogger(__name__)


class LinkedInPostsScraper(BaseScraper):
    """
    LinkedIn Hiring Posts Scraper — via Google Search.
    
    Mencari post publik di LinkedIn yang berisi info hiring/lowongan.
    Menggunakan query Google yang sangat spesifik untuk Indonesia.
    Filter ketat: TIDAK ada mock/fallback data palsu.
    """

    # Multi-keyword sets for comprehensive coverage
    SEARCH_TEMPLATES = [
        'site:linkedin.com/posts "{query}" ("Jakarta" OR "Indonesia" OR "Remote") ("hiring" OR "open position" OR "lowongan")',
        'site:linkedin.com/posts "{query}" "Indonesia" ("we are hiring" OR "join our team" OR "looking for")',
        'site:linkedin.com/feed/update "{query}" ("Jakarta" OR "Indonesia") ("hiring" OR "open position")',
    ]

    def search(self, query: str, location: str) -> list[dict]:
        logger.info(f"Searching LinkedIn hiring posts for '{query}' with strict Indonesia filter")
        raw_posts = []
        seen_urls = set()

        context = self._new_context("linkedin")
        page = context.new_page()
        page.set_default_timeout(30000)

        try:
            # Check if we have cookies in database to run direct search
            cookies = self.repository.get_platform_cookies("linkedin")
            if cookies:
                try:
                    raw_posts = self._search_direct(page, query, location)
                    if raw_posts:
                        logger.info(f"✅ Successfully collected {len(raw_posts)} posts directly from LinkedIn feed")
                        return raw_posts
                except Exception as direct_err:
                    logger.warning(f"Direct LinkedIn Posts scraping failed: {direct_err}. Falling back to Google Search Proxy.")

            # --- FALLBACK: GOOGLE SEARCH PROXY ---
            for template_idx, template in enumerate(self.SEARCH_TEMPLATES):
                if len(raw_posts) >= 15:
                    break

                search_query = template.replace("{query}", query)
                encoded = urllib.parse.quote(search_query)
                url = f"https://www.google.com/search?q={encoded}&num=15&hl=id"

                logger.info(f"LinkedIn Posts search template {template_idx + 1}/{len(self.SEARCH_TEMPLATES)}")
                
                try:
                    with google_search_lock:
                        logger.info("⏳ Acquiring Google Search Lock for LinkedIn Posts, waiting for cooldown...")
                        time.sleep(3)
                        page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    self.check_session_validity(page, "LinkedIn Posts")
                    page.wait_for_timeout(2000)

                    # Extract all LinkedIn post/feed links from Google results
                    links = page.query_selector_all("a[href*='linkedin.com/posts/']")
                    feed_links = page.query_selector_all("a[href*='linkedin.com/feed/update/']")
                    all_links = list(links) + list(feed_links)
                    
                    logger.info(f"Template {template_idx + 1}: found {len(all_links)} LinkedIn links")

                    for link in all_links:
                        try:
                            href = link.get_attribute("href") or ""
                            if not href:
                                continue

                            # Clean URL
                            clean_href = href.split("&")[0].split("?")[0]
                            
                            # Skip duplicate URLs
                            if clean_href in seen_urls:
                                continue
                            seen_urls.add(clean_href)

                            # === STRICT LOCATION FILTER on URL ===
                            url_lower = clean_href.lower()
                            
                            # Reject if URL contains foreign location indicators
                            url_has_foreign = any(loc.replace(" ", "-") in url_lower or loc.replace(" ", "") in url_lower 
                                                  for loc in EXCLUDE_LOCATIONS[:30])  # Check top 30 for URL
                            if url_has_foreign:
                                logger.debug(f"Skipped foreign-URL post: {clean_href}")
                                continue

                            # Try to get snippet text from parent element
                            snippet = ""
                            try:
                                parent = link.evaluate_handle("el => el.closest('div.g') || el.parentElement?.parentElement")
                                snippet = parent.inner_text() if parent else ""
                            except Exception:
                                try:
                                    snippet = link.inner_text().strip()
                                except Exception:
                                    pass

                            # === STRICT CONTENT FILTER ===
                            if snippet and not is_indonesia_relevant(snippet, clean_href):
                                logger.debug(f"Skipped non-Indonesia post: {clean_href}")
                                continue

                            raw_posts.append({
                                "post_url": clean_href,
                                "query_used": query,
                                "snippet": snippet,
                            })

                        except Exception as e:
                            logger.debug(f"Error extracting post link: {e}")

                except CookieExpiredException:
                    raise
                except Exception as e:
                    logger.warning(f"Google search template {template_idx + 1} failed: {e}")
                
                # Random delay between Google searches to avoid rate limiting
                if template_idx < len(self.SEARCH_TEMPLATES) - 1:
                    self.random_delay(1500, 3500)

        except CookieExpiredException:
            raise
        except Exception as e:
            logger.error(f"Error in LinkedIn Posts scraper: {e}")
        finally:
            context.close()

        logger.info(f"LinkedIn Posts found {len(raw_posts)} unique Indonesia-relevant posts")
        return raw_posts

    def _search_direct(self, page: Page, query: str, location: str) -> list[dict]:
        """Scrape LinkedIn hiring posts directly when logged in."""
        logger.info(f"Scraping LinkedIn Posts directly for '{query}' (logged-in)")
        import urllib.parse
        search_query = f'"{query}" (hiring OR lowongan OR open position) Indonesia'
        encoded_query = urllib.parse.quote(search_query)
        url = f"https://www.linkedin.com/search/results/content/?keywords={encoded_query}&origin=SWITCH_SEARCH_VERTICAL"
        
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        self.check_session_validity(page, "LinkedIn Posts")
        page.wait_for_timeout(5000)
        
        # Scroll to load dynamic posts
        self.auto_scroll(page, scroll_count=3, delay_ms=1500)
        
        post_blocks = (
            page.query_selector_all("div.search-content__feed-update")
            or page.query_selector_all("div.feed-shared-update-v2")
            or page.query_selector_all("[data-urn*='urn:li:activity:']")
        )
        
        logger.info(f"Direct LinkedIn Posts found {len(post_blocks)} post blocks")
        raw_posts = []
        for block in post_blocks:
            try:
                # Content
                content_el = (
                    block.query_selector(".feed-shared-update-v2__description")
                    or block.query_selector(".feed-shared-text")
                    or block.query_selector(".update-components-text")
                )
                content = content_el.inner_text().strip() if content_el else ""
                
                # Try to find link to the post
                link_el = (
                    block.query_selector("a[href*='/feed/update/urn:li:activity:']")
                    or block.query_selector("a.update-components-actor__image")
                )
                href = link_el.get_attribute("href") if link_el else ""
                post_url = ""
                if href:
                    if href.startswith("http"):
                        post_url = href.split("?")[0]
                    else:
                        post_url = f"https://www.linkedin.com{href}".split("?")[0]
                
                if not post_url:
                    # Fallback default url if not found, since a URL is required
                    urn = block.get_attribute("data-urn") or ""
                    if "urn:li:activity:" in urn:
                        activity_id = urn.split("urn:li:activity:")[1]
                        post_url = f"https://www.linkedin.com/feed/update/urn:li:activity:{activity_id}"
                    else:
                        continue
                
                # Author
                author_el = (
                    block.query_selector(".update-components-actor__title span[aria-hidden='true']")
                    or block.query_selector(".feed-shared-actor__title")
                )
                author_name = author_el.inner_text().strip() if author_el else "LinkedIn User"
                
                # Filter Indonesia keywords
                if content and is_indonesia_relevant(content, post_url):
                    raw_posts.append({
                        "post_url": post_url,
                        "query_used": query,
                        "snippet": content,
                        "author_name": author_name,
                    })
            except Exception as post_err:
                logger.debug(f"Error parsing direct LinkedIn post: {post_err}")
                
        return raw_posts

    def extract(self, element_or_page) -> dict:
        # Not used — extraction happens in search()
        return {}

    def normalize(self, raw_data: dict) -> dict:
        post_url = raw_data.get("post_url", "")
        snippet = raw_data.get("snippet", "")
        query_used = raw_data.get("query_used", "Software Engineer")
        
        if not post_url:
            return {}

        # === FINAL VALIDATION: Double-check Indonesia relevance ===
        combined = f"{snippet} {post_url}"
        if not is_indonesia_relevant(combined, post_url):
            logger.info(f"Normalize rejected non-Indonesia post: {post_url}")
            return {}

        # Build content from snippet or default
        content = snippet if snippet else f"Hiring for {query_used}. See post for details."

        # Extract author info from URL if possible
        author_name = "Recruiter / Hiring Manager"
        url_parts = post_url.split("/")
        for i, part in enumerate(url_parts):
            if part == "posts" and i + 1 < len(url_parts):
                # URL format: linkedin.com/posts/author-name-activity-123
                author_slug = url_parts[i + 1].split("-activity-")[0] if "-activity-" in url_parts[i + 1] else url_parts[i + 1]
                author_name = author_slug.replace("-", " ").title()
                break

        return {
            "author_name": author_name,
            "author_profile_url": "https://www.linkedin.com",
            "company": "LinkedIn Member",
            "content": content,
            "post_url": post_url,
        }

    def save(self, normalized_posts: list[dict]) -> list[dict]:
        return self.repository.save_linkedin_posts(normalized_posts)
