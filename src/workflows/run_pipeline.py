import logging
import time
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
    pipeline_start = time.time()
    logger.info("=" * 60)
    logger.info("  JOB HUNTER AGENT PIPELINE — START")
    logger.info("=" * 60)

    # 1. Init Database & Repo
    supabase_client = get_supabase_client()
    repo = JobRepository(supabase_client)

    # 2. Get User Profile
    user_profile = repo.get_user_profile()
    logger.info(f"Loaded User Profile — Skills: {user_profile.get('skills', [])}")
    logger.info(f"Preferred Roles: {user_profile.get('preferred_roles', [])}")
    logger.info(f"Preferred Locations: {user_profile.get('preferred_locations', [])}")

    queries = user_profile.get("preferred_roles", ["Backend Engineer"])
    locations = user_profile.get("preferred_locations", ["Indonesia"])
    primary_location = locations[0] if locations else "Indonesia"

    all_normalized_jobs = []
    all_normalized_posts = []
    platform_stats = {}  # Track stats per platform

    # 3. Playwright Scraping
    with sync_playwright() as p:
        # Define scraper mappings
        scrapers = {
            "LinkedIn Jobs": LinkedInScraper(p, repo),
            "Indeed": IndeedScraper(p, repo),
            "JobStreet": JobStreetScraper(p, repo),
            "Glints": GlintsScraper(p, repo),
            "Kalibrr": KalibrrScraper(p, repo),
        }

        # A. Run Job Scrapers
        for name, scraper in scrapers.items():
            repo.update_source_status(name, "RUNNING")
            scraper_start = time.time()
            try:
                platform_jobs = []
                for query in queries:
                    raw_data_list = scraper.search(query, primary_location)
                    for raw in raw_data_list:
                        normalized = scraper.normalize(raw)
                        if normalized:
                            platform_jobs.append(normalized)

                elapsed = round(time.time() - scraper_start, 1)
                platform_stats[name] = {"count": len(platform_jobs), "time": elapsed, "status": "SUCCESS"}
                logger.info(f"✅ {name}: {len(platform_jobs)} jobs in {elapsed}s")
                all_normalized_jobs.extend(platform_jobs)
                repo.update_source_status(name, "SUCCESS")
            except Exception as e:
                elapsed = round(time.time() - scraper_start, 1)
                platform_stats[name] = {"count": 0, "time": elapsed, "status": "FAILED"}
                logger.error(f"❌ {name}: FAILED in {elapsed}s — {e}")
                repo.update_source_status(name, "FAILED")
            finally:
                # Close browser after all queries for this scraper
                scraper.close_browser()

        # B. Run LinkedIn Posts Scraper
        posts_scraper = LinkedInPostsScraper(p, repo)
        repo.update_source_status("LinkedIn Posts", "RUNNING")
        scraper_start = time.time()
        try:
            for query in queries:
                raw_posts = posts_scraper.search(query, primary_location)
                for raw in raw_posts:
                    normalized = posts_scraper.normalize(raw)
                    if normalized:
                        all_normalized_posts.append(normalized)

            elapsed = round(time.time() - scraper_start, 1)
            platform_stats["LinkedIn Posts"] = {"count": len(all_normalized_posts), "time": elapsed, "status": "SUCCESS"}
            logger.info(f"✅ LinkedIn Posts: {len(all_normalized_posts)} posts in {elapsed}s")
            repo.update_source_status("LinkedIn Posts", "SUCCESS")
        except Exception as e:
            elapsed = round(time.time() - scraper_start, 1)
            platform_stats["LinkedIn Posts"] = {"count": 0, "time": elapsed, "status": "FAILED"}
            logger.error(f"❌ LinkedIn Posts: FAILED in {elapsed}s — {e}")
            repo.update_source_status("LinkedIn Posts", "FAILED")
        finally:
            posts_scraper.close_browser()

    # 4. Save Jobs to Database
    inserted_jobs = repo.save_jobs(all_normalized_jobs)
    logger.info(f"💾 Saved {len(inserted_jobs)} new jobs to database (from {len(all_normalized_jobs)} scraped).")

    # 5. Save LinkedIn Posts
    inserted_posts = repo.save_linkedin_posts(all_normalized_posts)
    logger.info(f"💾 Saved {len(inserted_posts)} new LinkedIn posts to database.")

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
            "matched_skills": matched_skills,
        })
        matched_jobs_report.append({
            "source": job["source"],
            "title": job["title"],
            "company": job["company"],
            "location": job["location"],
            "score": score,
            "matched_skills": matched_skills,
            "url": job["url"],
        })

    if matches_to_save:
        repo.save_job_matches(matches_to_save)
        logger.info(f"🎯 Saved {len(matches_to_save)} job matches.")

    # Process Posts Matches
    matched_posts_report = []
    for post in inserted_posts:
        score, matched_skills = matcher.calculate_score(post, is_post=True)
        matched_posts_report.append({
            "author_name": post["author_name"],
            "author_profile_url": post["author_profile_url"],
            "company": post["company"],
            "content": post["content"],
            "score": score,
            "matched_skills": matched_skills,
            "post_url": post["post_url"],
        })

    # 7. Sort matches
    matched_jobs_report.sort(key=lambda x: x["score"], reverse=True)
    matched_posts_report.sort(key=lambda x: x["score"], reverse=True)

    # 8. Send reports to Discord
    notifier = DiscordNotifier()
    notifier.send_report(matched_jobs_report, matched_posts_report)

    # 9. Print Summary
    total_elapsed = round(time.time() - pipeline_start, 1)
    logger.info("")
    logger.info("=" * 60)
    logger.info("  PIPELINE SUMMARY")
    logger.info("=" * 60)
    for name, stats in platform_stats.items():
        icon = "✅" if stats["status"] == "SUCCESS" else "❌"
        logger.info(f"  {icon} {name:20s} → {stats['count']:3d} items | {stats['time']}s | {stats['status']}")
    logger.info(f"  {'─' * 56}")
    logger.info(f"  📊 Total scraped:  {len(all_normalized_jobs)} jobs + {len(all_normalized_posts)} posts")
    logger.info(f"  💾 Total saved:    {len(inserted_jobs)} jobs + {len(inserted_posts)} posts")
    logger.info(f"  🎯 Total matched:  {len(matches_to_save)} job matches")
    logger.info(f"  ⏱️  Total time:     {total_elapsed}s")
    logger.info("=" * 60)
    logger.info("  JOB HUNTER AGENT PIPELINE — COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_pipeline()
