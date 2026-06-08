from abc import ABC, abstractmethod
from playwright.sync_api import Playwright
from src.database.repository import JobRepository

class BaseScraper(ABC):
    def __init__(self, playwright: Playwright, repository: JobRepository):
        self.playwright = playwright
        self.repository = repository

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
