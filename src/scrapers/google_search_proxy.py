"""
Google Search Proxy — shared utility for scrapers that use Google to find job listings.

Instead of scraping job sites directly (which often block headless browsers),
we search Google with `site:` operator and parse the search result snippets.
"""
import logging
import urllib.parse
import re
import threading
import time
from playwright.sync_api import Page

logger = logging.getLogger(__name__)

# Shared lock to synchronize all Google Search queries across thread workers
google_search_lock = threading.Lock()

# Lokasi asing yang harus di-exclude dari hasil
EXCLUDE_LOCATIONS = [
    "india", "pune", "bangalore", "bengaluru", "noida", "gurgaon",
    "hyderabad", "mumbai", "chennai", "delhi", "kolkata", "ahmedabad",
    "jaipur", "lucknow", "chandigarh", "thiruvananthapuram", "kochi",
    "coimbatore", "nagpur", "indore", "surat", "vadodara", "patna",
    "germany", "berlin", "munich", "hamburg", "frankfurt",
    "japan", "tokyo", "osaka",
    "usa", "united states", "new york", "san francisco", "seattle",
    "los angeles", "chicago", "austin", "boston", "denver",
    "uk", "united kingdom", "london", "manchester", "birmingham",
    "singapore",
    "malaysia", "kuala lumpur", "penang", "johor",
    "vietnam", "hanoi", "ho chi minh",
    "thailand", "bangkok",
    "philippines", "manila", "cebu",
    "china", "beijing", "shanghai", "shenzhen",
    "korea", "seoul",
    "taiwan", "taipei",
    "pakistan", "lahore", "karachi", "islamabad",
    "bangladesh", "dhaka",
    "sri lanka", "colombo",
    "nigeria", "lagos",
    "south africa", "cape town", "johannesburg",
    "dubai", "abu dhabi", "saudi", "riyadh",
    "canada", "toronto", "vancouver", "montreal",
    "australia", "sydney", "melbourne",
    "brazil", "são paulo",
    "mexico", "mexico city",
    "argentina", "buenos aires",
    "poland", "warsaw",
    "romania", "bucharest",
    "ukraine", "kyiv",
    "netherlands", "amsterdam",
    "france", "paris",
    "spain", "madrid", "barcelona",
    "italy", "milan", "rome",
    "portugal", "lisbon",
    "czech", "prague",
    "hungary", "budapest",
    "sweden", "stockholm",
    "norway", "oslo",
    "denmark", "copenhagen",
    "finland", "helsinki",
    "ireland", "dublin",
    "switzerland", "zurich",
    "austria", "vienna",
    "belgium", "brussels",
]

# Kata kunci Indonesia / valid
INDONESIA_KEYWORDS = [
    "indonesia", "jakarta", "tangerang", "bandung", "surabaya", "yogyakarta",
    "semarang", "medan", "makassar", "denpasar", "bali", "bogor", "depok",
    "bekasi", "malang", "solo", "salatiga", "palembang", "manado", "pontianak",
    "balikpapan", "batam", "pekanbaru", "lampung", "cirebon", "karawang",
    "cikarang", "serpong", "bsd", "gading serpong",
    "remote", "wfh", "wib", "rupiah", "idr",
]


def is_indonesia_relevant(text: str, url: str = "") -> bool:
    """Check if text/url is relevant to Indonesia and not a foreign location."""
    combined = (text + " " + url).lower()
    
    # Must mention at least one Indonesia keyword
    has_indo = any(kw in combined for kw in INDONESIA_KEYWORDS)
    
    # Check for foreign locations
    has_foreign = any(loc in combined for loc in EXCLUDE_LOCATIONS)
    
    # If has Indonesia keyword AND no foreign location → relevant
    # If has both → check if Indonesia is mentioned more prominently (keep it)
    if has_indo and not has_foreign:
        return True
    if has_indo and has_foreign:
        # Count occurrences — if Indonesia keywords appear more, keep it
        indo_count = sum(1 for kw in INDONESIA_KEYWORDS if kw in combined)
        foreign_count = sum(1 for loc in EXCLUDE_LOCATIONS if loc in combined)
        return indo_count > foreign_count
    
    return False


def google_search_jobs(
    page: Page,
    site_domain: str,
    query: str,
    location: str = "Indonesia",
    max_results: int = 20,
    extra_terms: str = "",
    time_range: str = "m3",
) -> list[dict]:
    """
    Search Google with site: operator and return parsed results.
    
    Returns list of dicts with keys: title, url, snippet, company (if parseable).
    """
    # Build search query
    search_parts = [f'site:{site_domain}']
    search_parts.append(f'"{query}"')
    
    # Add location constraint
    if location:
        search_parts.append(f'("{location}" OR "Jakarta" OR "Remote")')
    
    if extra_terms:
        search_parts.append(extra_terms)
    
    search_query = " ".join(search_parts)
    encoded = urllib.parse.quote(search_query)
    url = f"https://www.google.com/search?q={encoded}&num={max_results}&hl=id"
    if time_range:
        url += f"&tbs=qdr:{time_range}"
    
    logger.info(f"Google Search: {search_query}")
    
    results = []
    try:
        with google_search_lock:
            # Cooldown delay to prevent triggering CAPTCHA when multiple threads search Google
            logger.info("⏳ Acquiring Google Search Lock, waiting for cooldown...")
            time.sleep(3)
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            
        page.wait_for_timeout(2000 + (500 * len(query.split())))
        
        # Parse Google search results
        # Google result structure: div.g > div > div > a[href] + h3 + span/div (snippet)
        result_blocks = page.query_selector_all("div.g")
        
        if not result_blocks:
            # Fallback selector
            result_blocks = page.query_selector_all("[data-hveid] a[href*='" + site_domain.split("/")[0] + "']")
        
        logger.info(f"Google returned {len(result_blocks)} result blocks")
        
        for block in result_blocks[:max_results]:
            try:
                parsed = _parse_google_result(block, site_domain)
                if parsed and parsed.get("url"):
                    results.append(parsed)
            except Exception as e:
                logger.debug(f"Error parsing Google result block: {e}")
        
        # If div.g didn't work, try direct link extraction
        if not results:
            all_links = page.query_selector_all(f"a[href*='{site_domain}']")
            logger.info(f"Fallback: found {len(all_links)} direct links for {site_domain}")
            for link in all_links[:max_results]:
                try:
                    href = link.get_attribute("href") or ""
                    text = link.inner_text().strip()
                    if href and text and len(text) > 5:
                        clean_url = _clean_google_url(href)
                        if clean_url and site_domain in clean_url:
                            results.append({
                                "title": text.split("\n")[0].strip(),
                                "url": clean_url,
                                "snippet": text,
                                "company": "",
                            })
                except Exception as e:
                    logger.debug(f"Error extracting fallback link: {e}")
                    
    except Exception as e:
        logger.error(f"Google Search error for '{search_query}': {e}")
    
    logger.info(f"Google Search parsed {len(results)} results for {site_domain}")
    return results


def _parse_google_result(block, site_domain: str) -> dict | None:
    """Parse a single Google search result block (div.g)."""
    # Find the main link
    link_el = block.query_selector("a[href]")
    if not link_el:
        return None
    
    href = link_el.get_attribute("href") or ""
    clean_url = _clean_google_url(href)
    
    if not clean_url or site_domain not in clean_url:
        return None
    
    # Get title from h3
    title_el = block.query_selector("h3")
    title = title_el.inner_text().strip() if title_el else ""
    
    # Get snippet
    snippet_el = (
        block.query_selector("[data-sncf]")
        or block.query_selector("div[style*='-webkit-line-clamp']")
        or block.query_selector("span.st")
        or block.query_selector("div.VwiC3b")
    )
    snippet = snippet_el.inner_text().strip() if snippet_el else ""
    
    # Try to extract company from title or snippet
    company = _extract_company_from_title(title)
    
    return {
        "title": title,
        "url": clean_url,
        "snippet": snippet,
        "company": company,
    }


def _clean_google_url(href: str) -> str:
    """Clean Google redirect URLs to get the actual destination URL."""
    if href.startswith("/url?"):
        # Google redirect URL
        match = re.search(r'[?&]q=([^&]+)', href)
        if match:
            return urllib.parse.unquote(match.group(1))
    
    # Remove Google tracking params
    clean = href.split("&sa=")[0].split("&ved=")[0]
    return clean


def _extract_company_from_title(title: str) -> str:
    """Try to extract company name from Google result title.
    
    Common patterns:
    - "Job Title - Company Name | Platform"
    - "Job Title at Company Name - Platform"
    - "Company Name hiring Job Title in Location"
    """
    # Pattern: "Title - Company | Platform"
    if " | " in title:
        before_pipe = title.split(" | ")[0]
        if " - " in before_pipe:
            parts = before_pipe.rsplit(" - ", 1)
            if len(parts) == 2:
                return parts[1].strip()
    
    # Pattern: "Title at Company"
    if " at " in title.lower():
        match = re.search(r'\bat\b\s+(.+?)(?:\s*[-|]|$)', title, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    # Pattern: "Company hiring Title"
    if " hiring " in title.lower():
        match = re.search(r'^(.+?)\s+hiring\b', title, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    return ""
