import os
import sys

# Tambahkan root folder project ke path agar Python bisa mendeteksi folder "src"
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.workflows.run_pipeline import run_pipeline
from src.database.supabase_client import get_supabase_client
from src.database.repository import JobRepository
from playwright.sync_api import sync_playwright

def setup_logins():
    supabase_client = get_supabase_client()
    repo = JobRepository(supabase_client)
    
    platforms = [
        ("linkedin", "https://www.linkedin.com/login"),
        ("indeed", "https://id.indeed.com/"),
        ("jobstreet", "https://id.jobstreet.com/login")
    ]
    
    print("\n" + "="*50)
    print("🚀 PROSES SETUP LOGIN DIMULAI 🚀")
    print("="*50)
    
    with sync_playwright() as p:
        user_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chrome_profile")
        # Menggunakan launch_persistent_context agar tidak menggunakan mode incognito
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False, 
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled", "--no-default-browser-check"],
            ignore_default_args=["--enable-automation", "--no-sandbox"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )
        
        # Sembunyikan status otomatisasi dari Google
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)
        
        # Ambil tab pertama yang otomatis terbuka, atau buat tab baru
        page = context.pages[0] if context.pages else context.new_page()
        
        for name, url in platforms:
            print(f"\n[{name.upper()}] Membuka halaman login...")
            try:
                page.goto(url, timeout=60000)
            except Exception as e:
                print(f"Gagal memuat halaman: {e}")
                
            input(f"⏳ Silakan login ke {name.title()} di browser yang terbuka.\n▶️  TEKAN ENTER DI SINI JIKA SUDAH SELESAI LOGIN... ")
            
            cookies = context.cookies()
            repo.save_platform_cookies(name, cookies)
            print(f"✅ Sesi (Cookies) untuk {name.title()} berhasil disimpan ke database!")
            
        browser.close()
        
    print("\n✅ Semua setup login selesai! Anda bisa menjalankan scraping sekarang.")

if __name__ == "__main__":
    print("="*40)
    print("      MAIN MENU JOB HUNTER AGENT      ")
    print("="*40)
    print("1. Setup Login Manual (Simpan Sesi)")
    print("2. Mulai Proses Scraping (Auto)")
    print("="*40)
    
    choice = input("Pilih menu (1/2): ")
    if choice == "1":
        setup_logins()
    elif choice == "2":
        run_pipeline()
    else:
        print("Pilihan tidak valid.")
