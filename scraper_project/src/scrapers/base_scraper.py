import random
import time
import logging
from abc import ABC, abstractmethod
from playwright.sync_api import Playwright, Browser, BrowserContext, Page
from src.database.repository import JobRepository

from src.config.settings import settings

class CookieExpiredException(Exception):
    """Raised when session cookies are expired or a login wall is hit."""
    pass

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
    # _get_browser dihapus karena kita langsung menggunakan launch_persistent_context

    def _new_context(self, platform_name: str = None) -> BrowserContext:
        """Create a persistent context (bukan incognito) menggunakan profil Chrome utama."""
        import os
        
        # Gunakan User-Agent yang SAMA PERSIS dengan main.py (Setup Login)
        # Jika berubah-ubah, LinkedIn akan mendeteksi aktivitas mencurigakan dan me-logout sesi!
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        
        # Gunakan profil Chrome yang sama dengan proses "Setup Login" (opsi 1)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        user_data_dir = os.path.join(base_dir, "chrome_profile")
        
        launch_kwargs = {
            "headless": False,
            "channel": "chrome",
            "args": STEALTH_ARGS,
            "ignore_default_args": ["--enable-automation", "--no-sandbox"],
            "user_agent": ua,
            "viewport": {"width": 1280, "height": 800},
            "locale": "id-ID",
            "timezone_id": "Asia/Jakarta"
        }

        # Launch persistent context
        context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            **launch_kwargs
        )
        self._context = context
        
        # Karena kita menggunakan profil yang sama dengan "Setup Login", 
        # kita tidak perlu lagi menyuntikkan cookies dari database. 
        # Sesi Google SSO dll sudah menempel secara native.
        
        # Inject stealth script to mask navigator.webdriver
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
        """)
        return context

    def close_browser(self):
        """Close the persistent context when all queries are done."""
        if hasattr(self, '_context') and self._context:
            self._context.close()
            self._context = None

    def check_session_validity(self, page: Page, platform_name: str):
        """Verify if the browser context has been blocked or redirected to a login wall."""
        url = page.url.lower()
        if "google.com/sorry" in url:
            raise Exception("Google Search Proxy blocked (CAPTCHA/429). Please try again later or use proxies.")
            
        login_indicators = ["/login", "/signin", "/signup", "/checkpoint", "login.yahoo", "accounts.google", "authwall"]
        if any(term in url for term in login_indicators):
            logger.warning(f"⚠️ Akses ditolak atau belum login di '{platform_name}'.")
            
            # Karena proses sekarang berurutan (sequential), kita bisa mem-pause program 
            # sampai user selesai login secara manual di browser yang terbuka.
            print("\n" + "!"*60)
            print(f"🛑 [PERHATIAN] Sesi {platform_name} terdeteksi belum login atau expired!")
            print(f"Silakan buka jendela browser yang sedang berjalan sekarang dan login secara manual.")
            print("!"*60)
            
            input("▶️  TEKAN ENTER DI SINI JIKA KAMU SUDAH BERHASIL LOGIN... ")
            
            # Cek ulang URL setelah user menekan Enter
            new_url = page.url.lower()
            if any(term in new_url for term in login_indicators):
                raise CookieExpiredException(
                    f"Gagal memverifikasi login untuk '{platform_name}'. Masih berada di halaman login: {new_url}"
                )
            else:
                logger.info(f"✅ Sesi '{platform_name}' berhasil dilanjutkan setelah login manual.")

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
