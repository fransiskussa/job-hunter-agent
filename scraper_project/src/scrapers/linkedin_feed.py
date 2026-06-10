import logging
import time
from playwright.sync_api import Page
from src.scrapers.base_scraper import BaseScraper, CookieExpiredException
from src.scrapers.google_search_proxy import is_indonesia_relevant

logger = logging.getLogger(__name__)

class LinkedInHomeFeedScraper(BaseScraper):
    """
    Scraper untuk mencari lowongan langsung dari Home Feed (Beranda) LinkedIn milik user.
    """

    def search(self, query: str, location: str) -> list[dict]:
        logger.info(f"Mencari postingan lowongan di LinkedIn Home Feed...")
        raw_posts = []

        context = self._new_context("linkedin")
        page = context.new_page()
        page.set_default_timeout(30000)

        try:
            # Buka beranda LinkedIn
            url = "https://www.linkedin.com/feed/"
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            
            # Cek session
            self.check_session_validity(page, "LinkedIn Feed")
            
            # Tunggu loading awal
            page.wait_for_timeout(5000)
            
            # Scroll beranda beberapa kali untuk memuat postingan lama
            scroll_count = 10
            self.auto_scroll(page, scroll_count=scroll_count, delay_ms=2000)
            
            # Ambil elemen-elemen postingan
            post_blocks = (
                page.query_selector_all("div.feed-shared-update-v2")
                or page.query_selector_all("[data-urn*='urn:li:activity:']")
            )
            
            logger.info(f"Ditemukan {len(post_blocks)} blok postingan di Beranda LinkedIn.")
            
            # Kata kunci filter hiring umum
            hiring_keywords = [
                "hiring", "lowongan", "open position", "join our team", 
                "mencari", "dibutuhkan", "we are looking for", "urgently need", 
                "loker", "opportunity", "vacancy"
            ]
            
            for block in post_blocks:
                try:
                    # Ambil isi teks
                    content_el = (
                        block.query_selector(".feed-shared-update-v2__description")
                        or block.query_selector(".feed-shared-text")
                        or block.query_selector(".update-components-text")
                    )
                    content = content_el.inner_text().strip() if content_el else ""
                    
                    if not content:
                        continue
                        
                    content_lower = content.lower()
                    
                    # Cek apakah postingan mengandung kata kunci hiring
                    if not any(kw in content_lower for kw in hiring_keywords):
                        continue
                        
                    # Filter tambahan untuk memastikan konteks Indonesia (opsional)
                    # if not is_indonesia_relevant(content, ""):
                    #     continue
                        
                    # Ambil URL postingan
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
                    
                    # Jika tidak ada link, gunakan URN
                    if not post_url:
                        urn = block.get_attribute("data-urn") or ""
                        if "urn:li:activity:" in urn:
                            activity_id = urn.split("urn:li:activity:")[1]
                            post_url = f"https://www.linkedin.com/feed/update/urn:li:activity:{activity_id}"
                        else:
                            continue
                            
                    # Ambil Author Name
                    author_el = (
                        block.query_selector(".update-components-actor__title span[aria-hidden='true']")
                        or block.query_selector(".feed-shared-actor__title")
                        or block.query_selector(".update-components-actor__name")
                    )
                    author_name = author_el.inner_text().strip() if author_el else "LinkedIn User"
                    
                    # Simpan data mentah
                    raw_posts.append({
                        "post_url": post_url,
                        "query_used": "Home Feed",
                        "snippet": content,
                        "author_name": author_name,
                    })
                    
                except Exception as parse_err:
                    logger.debug(f"Error parsing postingan Feed: {parse_err}")
                    
        except CookieExpiredException:
            logger.warning("Session habis atau butuh login untuk LinkedIn Feed.")
        except Exception as e:
            logger.error(f"Error di LinkedIn Feed Scraper: {e}")
        finally:
            context.close()

        logger.info(f"Berhasil menyaring {len(raw_posts)} postingan lowongan dari Beranda.")
        return raw_posts

    def extract(self, element_or_page) -> dict:
        return {}

    def normalize(self, raw_data: dict) -> dict:
        post_url = raw_data.get("post_url", "")
        snippet = raw_data.get("snippet", "")
        author_name = raw_data.get("author_name", "Recruiter / Hiring Manager")
        
        if not post_url or not snippet:
            return {}

        return {
            "author_name": author_name,
            "author_profile_url": "https://www.linkedin.com",
            "company": "LinkedIn Network",
            "content": snippet,
            "post_url": post_url,
        }

    def save(self, normalized_posts: list[dict]) -> list[dict]:
        return self.repository.save_linkedin_posts(normalized_posts)
