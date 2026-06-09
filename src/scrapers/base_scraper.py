import random
import time
import logging
from abc import ABC, abstractmethod
from playwright.sync_api import Playwright, Browser, BrowserContext, Page
from src.database.repository import JobRepository

logger = logging.getLogger(__name__)

# Pool User-Agent untuk rotasi anti-detection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

# Chromium stealth args
STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-features=IsolateOrigins,site-per-process",
    "--disable-dev-shm-usage",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
    "--window-size=1280,800",
]


class BaseScraper(ABC):
    def __init__(self, playwright: Playwright, repository: JobRepository):
        self.playwright = playwright
        self.repository = repository
        self._browser: Browser | None = None

    # ── Browser Lifecycle ────────────────────────────────────────────
    def _get_browser(self) -> Browser:
        """Reuse a single browser instance across all queries for this scraper."""
        if self._browser is None or not self._browser.is_connected():
            self._browser = self.playwright.chromium.launch(
                headless=True,
                args=STEALTH_ARGS,
            )
        return self._browser

    def _new_context(self, platform_name: str = None) -> BrowserContext:
        """Create a fresh context with a random user-agent and optional cookies."""
        browser = self._get_browser()
        ua = random.choice(USER_AGENTS)
        context = browser.new_context(
            user_agent=ua,
            viewport={"width": 1280, "height": 800},
            locale="id-ID",
            timezone_id="Asia/Jakarta",
        )
        
        # Load cookies from DB if platform name is provided
        if platform_name:
            cookies = self.repository.get_platform_cookies(platform_name)
            if cookies:
                try:
                    context.add_cookies(cookies)
                    logger.info(f"🔑 Loaded cookies for platform '{platform_name}' from DB")
                except Exception as e:
                    logger.error(f"❌ Failed to load cookies for '{platform_name}' from DB: {e}")
            else:
                logger.warning(f"⚠️ No cookies found in DB for platform: '{platform_name}'")

        # Inject stealth script to mask navigator.webdriver
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
        """)
        return context

    def close_browser(self):
        """Close the browser when all queries are done."""
        if self._browser and self._browser.is_connected():
            self._browser.close()
            self._browser = None

    # ── Helpers ──────────────────────────────────────────────────────
    @staticmethod
    def random_delay(min_ms: int = 800, max_ms: int = 2500):
        """Human-like random delay between actions."""
        time.sleep(random.randint(min_ms, max_ms) / 1000)

    @staticmethod
    def auto_scroll(page: Page, scroll_count: int = 3, delay_ms: int = 1500):
        """Scroll down to trigger lazy-loaded content."""
        for i in range(scroll_count):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(delay_ms)
            logger.debug(f"Auto-scroll {i+1}/{scroll_count}")

    # ── Abstract Methods ─────────────────────────────────────────────
    @abstractmethod
    def search(self, query: str, location: str) -> list[dict]:
        """Perform search on the platform and return raw scraped entities."""
        pass

    @abstractmethod
    def extract(self, element_or_page) -> dict:
        """Extract attributes from a single job card or detail view."""
        pass

    @abstractmethod
    def normalize(self, raw_data: dict) -> dict:
        """Normalize raw platform data into common schema:
        {
            "source": str,
            "title": str,
            "company": str,
            "location": str,
            "description": str,
            "url": str,
            # optional metadata
            "salary": str (default None),
            "posted_date": str (default None)
        }
        """
        pass

    def save(self, normalized_jobs: list[dict]) -> list[dict]:
        """Save normalized jobs to Supabase."""
        return self.repository.save_jobs(normalized_jobs)
