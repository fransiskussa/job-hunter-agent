import logging
from playwright.sync_api import sync_playwright
from src.database.supabase_client import get_supabase_client
from src.database.repository import JobRepository
from src.scrapers.linkedin import LinkedInScraper
from src.scrapers.linkedin_posts import LinkedInPostsScraper
from src.scrapers.indeed import IndeedScraper
from src.scrapers.jobstreet import JobStreetScraper
from src.scrapers.glints import GlintsScraper
from src.scrapers.kalibrr import KalibrrScraper
from src.matching.matcher import JobMatcher
from src.discord.notifier import DiscordNotifier

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Pipeline")

def run_pipeline():
    logger.info("Initializing Job Hunter Agent Pipeline...")
    
    # 1. Init Database & Repo
    supabase_client = get_supabase_client()
    repo = JobRepository(supabase_client)
    
    # 2. Get User Profile
    user_profile = repo.get_user_profile()
    logger.info("Loaded User Profile successfully.")
    
    queries = user_profile.get("preferred_roles", ["Backend Engineer"])
    locations = user_profile.get("preferred_locations", ["Indonesia"])
    primary_location = locations[0] if locations else "Indonesia"
    
    all_normalized_jobs = []
    all_normalized_posts = []
    
    # 3. Playwright Scraping
    with sync_playwright() as p:
        # Define scraper mappings
        scrapers = {
            "LinkedIn Jobs": LinkedInScraper(p, repo),
            "Indeed": IndeedScraper(p, repo),
            "JobStreet": JobStreetScraper(p, repo),
            "Glints": GlintsScraper(p, repo),
            "Kalibrr": KalibrrScraper(p, repo)
        }
        
        # A. Run Job Scrapers
        for name, scraper in scrapers.items():
            repo.update_source_status(name, "RUNNING")
            try:
                platform_jobs = []
                for query in queries:
                    raw_data_list = scraper.search(query, primary_location)
                    for raw in raw_data_list:
                        normalized = scraper.normalize(raw)
                        if normalized:
                            platform_jobs.append(normalized)
                
                logger.info(f"Platform {name} collected {len(platform_jobs)} jobs.")
                all_normalized_jobs.extend(platform_jobs)
                repo.update_source_status(name, "SUCCESS")
            except Exception as e:
                logger.error(f"Error scraping platform {name}: {e}")
                repo.update_source_status(name, "FAILED")

        # B. Run LinkedIn Posts Scraper
        posts_scraper = LinkedInPostsScraper(p, repo)
        repo.update_source_status("LinkedIn Posts", "RUNNING")
        try:
            for query in queries:
                raw_posts = posts_scraper.search(query, primary_location)
                for raw in raw_posts:
                    normalized = posts_scraper.normalize(raw)
                    if normalized:
                        all_normalized_posts.append(normalized)
            
            logger.info(f"LinkedIn Posts collected {len(all_normalized_posts)} posts.")
            repo.update_source_status("LinkedIn Posts", "SUCCESS")
        except Exception as e:
            logger.error(f"Error scraping LinkedIn Posts: {e}")
            repo.update_source_status("LinkedIn Posts", "FAILED")
            
    # 4. Save Jobs to Database
    inserted_jobs = repo.save_jobs(all_normalized_jobs)
    logger.info(f"Saved {len(inserted_jobs)} new jobs to database.")
    
    # 5. Save LinkedIn Posts
    inserted_posts = repo.save_linkedin_posts(all_normalized_posts)
    logger.info(f"Saved {len(inserted_posts)} new LinkedIn posts to database.")
    
    # 6. Matching Engine
    matcher = JobMatcher(user_profile)
    matches_to_save = []
    
    # Process Jobs Matches
    matched_jobs_report = []
    for job in inserted_jobs:
        score, matched_skills = matcher.calculate_score(job, is_post=False)
        matches_to_save.append({
            "job_id": job["id"],
            "score": score,
            "matched_skills": matched_skills
        })
        matched_jobs_report.append({
            "source": job["source"],
            "title": job["title"],
            "company": job["company"],
            "location": job["location"],
            "score": score,
            "matched_skills": matched_skills,
            "url": job["url"]
        })
        
    if matches_to_save:
        repo.save_job_matches(matches_to_save)
        logger.info(f"Saved {len(matches_to_save)} job matches.")
        
    # Process Posts Matches
    matched_posts_report = []
    for post in inserted_posts:
        score, matched_skills = matcher.calculate_score(post, is_post=True)
        # Note: job_matches has foreign key to jobs table. Since linkedin_posts is a separate table,
        # we don't save their match relations into job_matches or we just track them for reports.
        # This keeps the schema clean as requested.
        matched_posts_report.append({
            "author_name": post["author_name"],
            "author_profile_url": post["author_profile_url"],
            "company": post["company"],
            "content": post["content"],
            "score": score,
            "matched_skills": matched_skills,
            "post_url": post["post_url"]
        })
        
    # 7. Sort Top 10 matches
    matched_jobs_report.sort(key=lambda x: x["score"], reverse=True)
    matched_posts_report.sort(key=lambda x: x["score"], reverse=True)
    
    # 8. Send reports to Discord
    notifier = DiscordNotifier()
    notifier.send_report(matched_jobs_report[:10], matched_posts_report[:10])
    logger.info("Pipeline Execution Completed.")

if __name__ == "__main__":
    run_pipeline()
