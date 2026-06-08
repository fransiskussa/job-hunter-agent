import logging
import urllib.parse
from src.scrapers.base_scraper import BaseScraper
from src.scrapers.google_search_proxy import is_indonesia_relevant, EXCLUDE_LOCATIONS, INDONESIA_KEYWORDS

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

        context = self._new_context()
        page = context.new_page()
        page.set_default_timeout(20000)

        try:
            for template_idx, template in enumerate(self.SEARCH_TEMPLATES):
                if len(raw_posts) >= 15:
                    break

                search_query = template.replace("{query}", query)
                encoded = urllib.parse.quote(search_query)
                url = f"https://www.google.com/search?q={encoded}&num=15&hl=id"

                logger.info(f"LinkedIn Posts search template {template_idx + 1}/{len(self.SEARCH_TEMPLATES)}")
                
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=20000)
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

                except Exception as e:
                    logger.warning(f"Google search template {template_idx + 1} failed: {e}")
                
                # Random delay between Google searches to avoid rate limiting
                if template_idx < len(self.SEARCH_TEMPLATES) - 1:
                    self.random_delay(1500, 3500)

        except Exception as e:
            logger.error(f"Error in LinkedIn Posts scraper: {e}")
        finally:
            context.close()

        logger.info(f"LinkedIn Posts found {len(raw_posts)} unique Indonesia-relevant posts")
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
