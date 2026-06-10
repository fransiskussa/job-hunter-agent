import re
import logging

logger = logging.getLogger(__name__)

# Konfigurasi Default yang mudah di-tune tanpa mengubah kode logika utama
DEFAULT_CONFIG = {
    "weights": {
        "skills": 50,      # Bobot maksimal untuk kecocokan skill
        "role": 20,        # Bobot maksimal untuk kecocokan role/posisi
        "location": 10,    # Bobot maksimal untuk kecocokan lokasi
        "seniority": 10,   # Bobot maksimal untuk tingkat seniority
        "keywords": 10     # Bobot maksimal untuk kecocokan kata kunci bonus
    },
    "role_aliases": {
        "backend engineer": ["backend", "api", "server", "python", "golang", "node", "django", "fastapi"],
        "software engineer": ["software engineer", "developer", "programmer", "engineer"],
        "fullstack developer": ["fullstack", "full-stack", "frontend", "backend", "web developer"],
        "frontend engineer": ["frontend", "front-end", "react", "vue", "javascript", "typescript", "ui developer"]
    },
    "weighted_keywords": {
        "remote": 4,
        "wfh": 4,
        "urgent": 5,
        "urgently": 5,
        "immediately": 5,
        "bonus": 1,
        "fulltime": 2,
        "full-time": 2,
        "hybrid": 1,
        "wfo": 1
    },
    "seniority": {
        "senior_keywords": ["senior", "lead", "principal", "staff", "manager", "sr", "head"],
        "junior_keywords": ["junior", "intern", "associate", "fresh", "entry", "jr", "trainee"]
    },
    "low_score_pool_min": 5,    # Nilai minimum jika masuk low-score pool (misal lolos kriteria sekunder)
    "low_score_pool_max": 15    # Nilai maksimum jika masuk low-score pool
}


class JobMatcher:
    def __init__(self, user_profile: dict, config: dict | None = None):
        self.user_profile = user_profile
        self.config = config or DEFAULT_CONFIG
        
        self.user_skills = [s.lower() for s in user_profile.get("skills", [])]
        self.preferred_roles = [r.lower() for r in user_profile.get("preferred_roles", [])]
        self.preferred_locations = [l.lower() for l in user_profile.get("preferred_locations", [])]

    def calculate_score(self, job_or_post: dict, is_post: bool = False) -> tuple[int, list[str], dict]:
        """
        Menghitung skor kecocokan antara lowongan dengan profil pengguna (skala 0-100).
        Mengembalikan tuple: (total_score, matched_skills, score_breakdown)
        """
        # Penanganan nilai None secara defensif agar tidak terjadi AttributeError
        title = (job_or_post.get("title") or "").strip() if not is_post else "LinkedIn Post"
        description = (job_or_post.get("description") or "").strip() if not is_post else (job_or_post.get("content") or "").strip()
        location = (job_or_post.get("location") or "").strip() if not is_post else "Indonesia (Remote / Post)"

        title_lower = title.lower()
        description_lower = description.lower()
        location_lower = location.lower()

        # Load Weights dari Konfigurasi
        weights = self.config.get("weights", DEFAULT_CONFIG["weights"])

        # ─── 1. SKILLS MATCHING (Bobot Maksimal: weights["skills"]) ───
        regex_matched_skills = []
        for skill in self.user_skills:
            escaped_skill = re.escape(skill)
            # Menangani simbol khusus pemrograman secara aman
            if any(char in skill for char in ["+", "#", ".", "/"]):
                pattern = rf"(?:^|[\s/,\-\(\)])({escaped_skill})(?:$|[\s/,\-\(\)])"
            else:
                pattern = rf"\b{escaped_skill}\b"
                
            if re.search(pattern, title_lower) or re.search(pattern, description_lower):
                # Ambil format nama skill asli dari profil user
                orig_skill = next((s for s in self.user_profile.get("skills", []) if s.lower() == skill), skill)
                regex_matched_skills.append(orig_skill)

        skills_ratio = len(regex_matched_skills) / max(1, len(self.user_skills))
        skills_score = round(skills_ratio * weights.get("skills", 50))

        # ─── 2. IMPROVED ROLE MATCHING (Bobot Maksimal: weights["role"]) ───
        role_score = 0
        has_role_match = False
        text_to_check = title_lower if not is_post else description_lower
        
        # Dapatkan pemetaan alias role
        role_aliases = self.config.get("role_aliases", DEFAULT_CONFIG["role_aliases"])
        
        for pref_role in self.preferred_roles:
            # Check 1: Match langsung (string contains)
            if pref_role in text_to_check:
                has_role_match = True
                break
            
            # Check 2: Match menggunakan alias mapping
            aliases = role_aliases.get(pref_role, [])
            if any(alias in text_to_check for alias in aliases):
                has_role_match = True
                break

        if has_role_match:
            role_score = weights.get("role", 20)

        # ─── 3. LOCATION MATCHING (Bobot Maksimal: weights["location"]) ───
        location_score = 0
        for loc in self.preferred_locations:
            if loc in location_lower or (loc == "remote" and ("remote" in title_lower or "remote" in description_lower)):
                location_score = weights.get("location", 10)
                break

        # ─── 4. SENIORITY MATCHING (Bobot Maksimal: weights["seniority"]) ───
        seniority_cfg = self.config.get("seniority", DEFAULT_CONFIG["seniority"])
        senior_keywords = seniority_cfg.get("senior_keywords", [])
        junior_keywords = seniority_cfg.get("junior_keywords", [])

        # Deteksi level pekerjaan berdasarkan judul
        job_is_senior = any(w in title_lower for w in senior_keywords)
        job_is_junior = any(w in title_lower for w in junior_keywords)
        job_seniority = "senior" if job_is_senior else ("junior" if job_is_junior else "neutral")

        # Deteksi preferensi user berdasarkan role yang diincar
        pref_is_senior = any(any(w in r for w in senior_keywords) for r in self.preferred_roles)
        pref_is_junior = any(any(w in r for w in junior_keywords) for r in self.preferred_roles)
        user_seniority = "senior" if pref_is_senior else ("junior" if pref_is_junior else "neutral")

        # Logika penilaian kecocokan tingkat pengalaman yang adil (tidak random)
        seniority_score = 0
        max_seniority_pts = weights.get("seniority", 10)

        if user_seniority == job_seniority:
            # Cocok sempurna (Senior-Senior, Junior-Junior, atau Neutral-Neutral)
            seniority_score = max_seniority_pts
        elif user_seniority == "neutral" or job_seniority == "neutral":
            # Salah satunya netral (masih sangat relevan)
            seniority_score = round(max_seniority_pts * 0.7)
        else:
            # Tidak cocok (Contoh: User Junior melamar Senior, atau sebaliknya)
            seniority_score = 0

        # ─── 5. WEIGHTED KEYWORD SYSTEM (Bobot Maksimal: weights["keywords"]) ───
        weighted_keywords = self.config.get("weighted_keywords", DEFAULT_CONFIG["weighted_keywords"])
        keyword_score = 0
        total_keyword_weight_hit = 0
        
        for kw, weight in weighted_keywords.items():
            if kw in title_lower or kw in description_lower:
                total_keyword_weight_hit += weight
        
        # Normalisasi nilai kata kunci ke skala bobot maksimal (maksimum hit rate dianggap bernilai 15 untuk normalisasi)
        if total_keyword_weight_hit > 0:
            keyword_score = min(weights.get("keywords", 10), round((total_keyword_weight_hit / 15.0) * weights.get("keywords", 10)))

        # ─── 6. HARD FILTER & LOW-SCORE POOL HANDLING ───
        # Low-score pool diaktifkan jika tidak ada kecocokan skill ATAU role utama.
        # Alih-alih langsung memberi nilai 0, lowongan dengan kriteria sekunder (lokasi/keyword) yang baik tetap masuk pool kecil.
        is_poor_match = (not regex_matched_skills) and (not has_role_match)
        
        if is_poor_match:
            # Hitung nilai sekunder kasar
            secondary_sum = location_score + keyword_score
            min_pool = self.config.get("low_score_pool_min", 5)
            max_pool = self.config.get("low_score_pool_max", 15)
            
            if secondary_sum > 0:
                # Berikan skor minimal di rentang pool rendah agar tidak langsung dibuang
                final_score = min(max_pool, max(min_pool, secondary_sum))
            else:
                final_score = 0
            
            breakdown = {
                "skills": 0,
                "role": 0,
                "location": 0,
                "seniority": 0,
                "keyword": 0,
                "low_score_pool_applied": True
            }
            return final_score, regex_matched_skills, breakdown

        # Perhitungan Skor Total untuk Pekerjaan Relevan
        total_score = skills_score + role_score + location_score + seniority_score + keyword_score

        # ─── 7. LinkedIn Post Boost ───
        boost_applied = False
        if is_post:
            post_content = description_lower
            boost_terms = ["hiring immediately", "urgently hiring", "remote", "open position", "referral", "recruiter contact"]
            for term in boost_terms:
                if term in post_content:
                    total_score += 15
                    boost_applied = True
                    break

        total_score = min(100, total_score)

        # ─── 8. Pembuatan Score Breakdown (Debugging) ───
        breakdown = {
            "skills": skills_score,
            "role": role_score,
            "location": location_score,
            "seniority": seniority_score,
            "keyword": keyword_score,
            "linkedin_boost_applied": boost_applied,
            "low_score_pool_applied": False
        }

        return total_score, regex_matched_skills, breakdown
