import logging
import time
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright
from src.database.supabase_client import get_supabase_client
from src.database.repository import JobRepository
from src.scrapers.linkedin import LinkedInScraper
from src.scrapers.linkedin_posts import LinkedInPostsScraper
from src.scrapers.indeed import IndeedScraper
from src.scrapers.jobstreet import JobStreetScraper
from src.scrapers.glints import GlintsScraper
from src.scrapers.kalibrr import KalibrrScraper
from src.scrapers.base_scraper import CookieExpiredException
from src.matching.matcher import JobMatcher
from src.discord.notifier import DiscordNotifier
from src.exports.google_sheets import GoogleSheetsExporter

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Pipeline")


def scrape_platform_worker(platform_name, scraper_class, queries, primary_location, repo, notifier, matcher):
    logger.info(f"🧵 Thread started for scraper: {platform_name}")
    platform_jobs = []
    scraper_start = time.time()
    repo.update_source_status(platform_name, "RUNNING")
    
    try:
        with sync_playwright() as p:
            scraper = scraper_class(p, repo)
            normalized_dropped_count = 0
            
            # ---------------------------------------------------------
            # MANUAL PRE-LOGIN PROMPT
            # Buka homepage sebentar untuk memberi kesempatan user login
            # ---------------------------------------------------------
            # homepages = {
            #     "Indeed": "https://id.indeed.com/",
            #     "JobStreet": "https://id.jobstreet.com/login",
            #     "Glints": "https://glints.com/id",
            #     "Kalibrr": "https://www.kalibrr.com/login",
            #     "LinkedIn Jobs": "https://www.linkedin.com/login"
            # }
            # if platform_name in homepages:
            #     context = scraper._new_context(platform_name)
            #     page = context.new_page()
            #     try:
            #         page.goto(homepages[platform_name], timeout=60000)
            #     except Exception:
            #         pass
            #     print("\n" + "="*50)
            #     print(f"🛑 [PAUSE LOGIN] Membuka {platform_name}.")
            #     print(f"Silakan cek browser. Jika belum login, silakan login sekarang.")
            #     print(f"Jika SUDAH LOGIN, langsung tekan Enter saja.")
            #     print("="*50)
            #     input("▶️  TEKAN ENTER DI SINI UNTUK MEMULAI SCRAPING... ")
            #     context.close()
            # ---------------------------------------------------------

            for query in queries:
                if len(platform_jobs) >= 50:
                    break
                raw_data_list = scraper.search(query, primary_location)
                for raw in raw_data_list:
                    if len(platform_jobs) >= 50:
                        break
                    normalized = scraper.normalize(raw)
                    if normalized:
                        score, matched_skills, breakdown = matcher.calculate_score(normalized, is_post=False)
                        # Tanpa filter ketat, semua lowongan hasil pencarian dimasukkan
                        platform_jobs.append(normalized)
                    else:
                        normalized_dropped_count += 1
                        logger.warning(f"[{platform_name}] ⚠️ Data dropped silently during normalize(): {raw.get('title', 'Unknown')} -> {raw.get('url', '')}")
            scraper.close_browser()
            
        elapsed = round(time.time() - scraper_start, 1)
        if normalized_dropped_count > 0:
            logger.info(f"[{platform_name}] 📉 normalization dropped {normalized_dropped_count} items total.")
        logger.info(f"✅ {platform_name}: {len(platform_jobs)} jobs in {elapsed}s")
        repo.update_source_status(platform_name, "SUCCESS")
        return platform_name, platform_jobs, elapsed, "SUCCESS"
    except CookieExpiredException as e:
        elapsed = round(time.time() - scraper_start, 1)
        logger.error(f"❌ {platform_name}: Cookie expired/Login required! — {e}")
        repo.update_source_status(platform_name, "FAILED")
        
        # Send warning to Discord
        try:
            notifier.send_warning(
                f"Cookie session for **{platform_name}** has expired or hit a login wall! "
                f"Please update the cookie values in your Supabase `platform_sessions` table.\n"
                f"Error details: `{e}`"
            )
        except Exception as dn_err:
            logger.error(f"Failed to send Discord alert: {dn_err}")
            
        return platform_name, [], elapsed, "COOKIE_EXPIRED"
    except Exception as e:
        elapsed = round(time.time() - scraper_start, 1)
        logger.error(f"❌ {platform_name}: FAILED in {elapsed}s — {e}")
        repo.update_source_status(platform_name, "FAILED")
        
        # Check if CAPTCHA or blocked
        if "captcha" in str(e).lower() or "blocked" in str(e).lower():
            try:
                notifier.send_warning(f"Scraper **{platform_name}** has been blocked or encountered a CAPTCHA wall.\nError details: `{e}`")
            except Exception:
                pass
                
        return platform_name, [], elapsed, "FAILED"


def scrape_posts_worker(platform_name, scraper_class, queries, primary_location, repo, notifier, matcher):
    logger.info(f"🧵 Thread started for scraper: {platform_name}")
    platform_posts = []
    scraper_start = time.time()
    repo.update_source_status(platform_name, "RUNNING")
    
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            posts_scraper = scraper_class(p, repo)
            normalized_dropped_count = 0
            
            # ---------------------------------------------------------
            # MANUAL PRE-LOGIN PROMPT
            # Buka homepage sebentar untuk memberi kesempatan user login
            # ---------------------------------------------------------
            # if "LinkedIn" in platform_name:
            #     context = posts_scraper._new_context(platform_name)
            #     page = context.new_page()
            #     try:
            #         page.goto("https://www.linkedin.com/login", timeout=60000)
            #     except Exception:
            #         pass
            #     print("\n" + "="*50)
            #     print(f"🛑 [PAUSE LOGIN] Membuka {platform_name}.")
            #     print(f"Silakan cek browser. Jika belum login, silakan login sekarang.")
            #     print(f"Jika SUDAH LOGIN, langsung tekan Enter saja.")
            #     print("="*50)
            #     input("▶️  TEKAN ENTER DI SINI UNTUK MEMULAI SCRAPING... ")
            #     context.close()
            # ---------------------------------------------------------
            
            # For Home Feed, we only need to search once (queries don't matter)
            effective_queries = queries if platform_name != "LinkedIn Home Feed" else ["Home Feed"]
            
            for query in effective_queries:
                if len(platform_posts) >= 50:
                    break
                raw_posts = posts_scraper.search(query, primary_location)
                for raw in raw_posts:
                    if len(platform_posts) >= 50:
                        break
                    normalized = posts_scraper.normalize(raw)
                    if normalized:
                        score, matched_skills, breakdown = matcher.calculate_score(normalized, is_post=True)
                        platform_posts.append(normalized)
                    else:
                        normalized_dropped_count += 1
                        logger.warning(f"[{platform_name}] ⚠️ Post dropped silently during normalize(): {raw.get('post_url', '')}")
            posts_scraper.close_browser()
            
        elapsed = round(time.time() - scraper_start, 1)
        if normalized_dropped_count > 0:
            logger.info(f"[{platform_name}] 📉 normalization dropped {normalized_dropped_count} posts total.")
        logger.info(f"✅ {platform_name}: {len(platform_posts)} posts in {elapsed}s")
        repo.update_source_status(platform_name, "SUCCESS")
        return platform_name, platform_posts, elapsed, "SUCCESS"
    except CookieExpiredException as e:
        elapsed = round(time.time() - scraper_start, 1)
        logger.error(f"❌ {platform_name}: Cookie expired/Login required! — {e}")
        repo.update_source_status(platform_name, "FAILED")
        return platform_name, [], elapsed, "COOKIE_EXPIRED"
    except Exception as e:
        elapsed = round(time.time() - scraper_start, 1)
        logger.error(f"❌ {platform_name}: FAILED in {elapsed}s — {e}")
        repo.update_source_status(platform_name, "FAILED")
        return platform_name, [], elapsed, "FAILED"


def run_pipeline():
    pipeline_start = time.time()
    logger.info("=" * 60)
    logger.info("  JOB HUNTER AGENT PIPELINE — START (PARALLEL MODE)")
    logger.info("=" * 60)

    # 1. Init Database & Repo
    supabase_client = get_supabase_client()
    repo = JobRepository(supabase_client)
    notifier = DiscordNotifier()

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

    # Define job scraper classes
    job_scrapers = {
        "LinkedIn Jobs": LinkedInScraper,  # Di-skip sementara
        "Indeed": IndeedScraper,
        "JobStreet": JobStreetScraper,
        "Glints": GlintsScraper,
        "Kalibrr": KalibrrScraper,
    }
    
    # Define posts scraper classes
    from src.scrapers.linkedin_feed import LinkedInHomeFeedScraper
    post_scrapers = {
        "LinkedIn Posts": LinkedInPostsScraper, # Di-skip sementara
        "LinkedIn Home Feed": LinkedInHomeFeedScraper, # Di-skip sementara
    }

    # 3. Matcher Init Early for Pre-Filtering
    matcher = JobMatcher(user_profile)

    # 4. Sequential Scrapers Execution (Untuk menghindari bentrok profil Chrome)
    logger.info("Mulai mengeksekusi scraper secara berurutan...")
    
    # Run all job scrapers sequentially
    for name, scraper_class in job_scrapers.items():
        try:
            p_name, items, elapsed, status = scrape_platform_worker(
                name,
                scraper_class,
                queries,
                primary_location,
                repo,
                notifier,
                matcher
            )
            platform_stats[p_name] = {"count": len(items), "time": elapsed, "status": status}
            all_normalized_jobs.extend(items)
        except Exception as exc:
            logger.error(f"Scraper {name} generated an unhandled exception: {exc}")
            
    # Run all post scrapers sequentially
    for name, scraper_class in post_scrapers.items():
        try:
            p_name, items, elapsed, status = scrape_posts_worker(
                name,
                scraper_class,
                queries,
                primary_location,
                repo,
                notifier,
                matcher
            )
            platform_stats[p_name] = {"count": len(items), "time": elapsed, "status": status}
            all_normalized_posts.extend(items)
        except Exception as exc:
            logger.error(f"Scraper {name} generated an unhandled exception: {exc}")

    # 5. Save Jobs to Database
    inserted_jobs = repo.save_jobs(all_normalized_jobs)
    logger.info(f"💾 Saved {len(inserted_jobs)} new jobs to database (from {len(all_normalized_jobs)} pre-filtered).")

    # Save LinkedIn Posts
    inserted_posts = repo.save_linkedin_posts(all_normalized_posts)
    logger.info(f"💾 Saved {len(inserted_posts)} new LinkedIn posts to database.")

    # 6. Process Jobs Matches
    matches_to_save = []
    matched_jobs_report = []

    for job in inserted_jobs:
        score, matched_skills, breakdown = matcher.calculate_score(job, is_post=False)
        logger.info(f"📊 Job: '{job.get('title')}' @ {job.get('company')} | Score: {score} | Breakdown: {breakdown}")
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

    # 7. Sort matches
    matched_jobs_report.sort(key=lambda x: x["score"], reverse=True)

    matched_posts_report = []
    for post in inserted_posts:
        score, matched_skills, breakdown = matcher.calculate_score(post, is_post=True)
        matched_posts_report.append({
            "source": "LinkedIn Posts",
            "title": f"Post by {post['author_name']}",
            "company": post["company"] or "-",
            "location": "Indonesia",
            "score": score,
            "matched_skills": matched_skills,
            "url": post["post_url"],
            
            # keep original fields for discord
            "author_name": post["author_name"],
            "author_profile_url": post["author_profile_url"],
            "content": post["content"],
            "post_url": post["post_url"],
        })

    matched_posts_report.sort(key=lambda x: x["score"], reverse=True)

    # 8. Export to Google Sheets (Combine Jobs and Posts)
    sheets_exporter = GoogleSheetsExporter()
    combined_for_sheets = matched_jobs_report + matched_posts_report
    combined_for_sheets.sort(key=lambda x: x["score"], reverse=True)
    sheets_exporter.export_jobs(combined_for_sheets)

    # 9. Send reports to Discord
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
    logger.info(f"  📊 Total pre-filtered scraped: {len(all_normalized_jobs)} jobs")
    logger.info(f"  💾 Total saved:                {len(inserted_jobs)} jobs")
    logger.info(f"  🎯 Total matched:              {len(matches_to_save)} job matches")
    logger.info(f"  ⏱️  Total time:                 {total_elapsed}s")
    logger.info("=" * 60)
    logger.info("  JOB HUNTER AGENT PIPELINE — COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    run_pipeline()
