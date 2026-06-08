import os
import re
import json
import glob
import logging
import google.generativeai as genai
from pypdf import PdfReader

logger = logging.getLogger(__name__)

class JobMatcher:
    def __init__(self, user_profile: dict):
        self.user_profile = user_profile
        self.user_skills = [s.lower() for s in user_profile.get("skills", [])]
        self.preferred_roles = [r.lower() for r in user_profile.get("preferred_roles", [])]
        self.preferred_locations = [l.lower() for l in user_profile.get("preferred_locations", [])]
        
        # Inisialisasi Gemini AI jika API Key tersedia
        self.api_key = os.getenv("GEMINI_API_KEY")
        if self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel('gemini-1.5-flash')
                logger.info("AI Matching Engine initialized with Gemini API.")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini: {e}")
                self.model = None
        else:
            self.model = None
            logger.info("Gemini API Key not found. Using Rule-Based Matching Engine.")

        # Ekstrak konten teks dari file CV PDF lokal jika ada
        self.cv_text = self._extract_cv_text()
        if self.cv_text:
            logger.info("Local CV PDF detected and parsed successfully.")
        else:
            logger.info("No local CV PDF detected. Matching will fallback to Supabase profile skills.")

    def _extract_cv_text(self) -> str:
        """Mencari file PDF CV di root folder dan mengekstrak teksnya."""
        # Cari file PDF yang diawali kata "CV" di root repo atau folder kerja
        pdf_paths = glob.glob("CV*.pdf") + glob.glob("new/CV*.pdf") + glob.glob("../CV*.pdf")
        if not pdf_paths:
            return ""
        
        pdf_path = pdf_paths[0]
        try:
            reader = PdfReader(pdf_path)
            text = ""
            for page in reader.pages:
                text_content = page.extract_text()
                if text_content:
                    text += text_content + "\n"
            return text.strip()
        except Exception as e:
            logger.error(f"Error reading PDF CV: {e}")
            return ""

    def calculate_score(self, job_or_post: dict, is_post: bool = False) -> tuple[int, list[str]]:
        """Hitung skor kecocokan. Menggunakan Gemini AI jika tersedia, jika tidak fallback ke Rule-Based."""
        if self.model and (self.cv_text or self.user_profile):
            return self._calculate_ai_score(job_or_post, is_post)
        else:
            return self._calculate_rule_based_score(job_or_post, is_post)

    def _calculate_ai_score(self, job_or_post: dict, is_post: bool = False) -> tuple[int, list[str]]:
        """Gunakan Gemini AI untuk membandingkan langsung CV PDF Anda dengan lowongan kerja."""
        title = job_or_post.get("title", "") if not is_post else "LinkedIn Post"
        description = job_or_post.get("description", "") if not is_post else job_or_post.get("content", "")
        location = job_or_post.get("location", "Indonesia")
        company = job_or_post.get("company", "Unknown")

        # Jika CV PDF tidak terdeteksi, gunakan informasi text list profile dari Supabase
        profile_context = f"Daftar Keahlian: {', '.join(self.user_skills)}"
        if self.cv_text:
            profile_context = f"Konten CV Asli:\n{self.cv_text}"

        prompt = f"""
        Bertindaklah sebagai Senior Technical Recruiter. Evaluasi kecocokan antara Profil/CV Kandidat dan Lowongan Kerja berikut.

        [PROFIL / CV KANDIDAT]
        {profile_context}

        [LOWONGAN KERJA]
        - Judul: {title}
        - Perusahaan: {company}
        - Lokasi: {location}
        - Deskripsi Pekerjaan: {description}

        Tugas Anda:
        1. Hitung skor kecocokan kandidat dengan pekerjaan (skala 0 - 100). Berikan nilai secara ketat dan jujur.
        2. Tentukan daftar keahlian kandidat (maksimal 6) yang benar-benar cocok dan relevan dengan posisi tersebut.

        Kembalikan respon HANYA dalam format JSON mentah tanpa format Markdown atau penjelasan tambahan seperti berikut:
        {{
          "score": 85,
          "matched_skills": ["Python", "Docker", "PostgreSQL"]
        }}
        """

        try:
            response = self.model.generate_content(prompt)
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_text)
            
            score = int(data.get("score", 0))
            matched_skills = data.get("matched_skills", [])
            return min(100, max(0, score)), matched_skills
        except Exception as e:
            logger.error(f"Gemini evaluation error (falling back to Rule-Based): {e}")
            return self._calculate_rule_based_score(job_or_post, is_post)

    def _calculate_rule_based_score(self, job_or_post: dict, is_post: bool = False) -> tuple[int, list[str]]:
        """Sistem kalkulasi cadangan berbasis pencocokan kata kunci (Rule-Based)."""
        title = job_or_post.get("title", "").lower() if not is_post else job_or_post.get("content", "").lower()
        description = job_or_post.get("description", "").lower() if not is_post else job_or_post.get("content", "").lower()
        location = job_or_post.get("location", "").lower() if not is_post else ""

        # 1. Skills Match (50%)
        matched_skills = []
        for skill in self.user_skills:
            escaped_skill = re.escape(skill)
            if any(char in skill for char in ["+", "#", ".", "/"]):
                pattern = rf"(?:^|[\s/,\-\(\)])({escaped_skill})(?:$|[\s/,\-\(\)])"
            else:
                pattern = rf"\b{escaped_skill}\b"
                
            if re.search(pattern, title) or re.search(pattern, description):
                orig_skill = next((s for s in self.user_profile.get("skills", []) if s.lower() == skill), skill)
                matched_skills.append(orig_skill)

        skills_ratio = len(matched_skills) / max(1, len(self.user_skills))
        skills_score = int(skills_ratio * 50)

        # 2. Role Match (20%)
        role_score = 0
        text_to_check = title if not is_post else description
        for role in self.preferred_roles:
            if role in text_to_check:
                role_score = 20
                break

        # 3. Location Match (10%)
        location_score = 0
        for loc in self.preferred_locations:
            if loc in location or (loc == "remote" and ("remote" in title or "remote" in description)):
                location_score = 10
                break

        # 4. Seniority Match (10%)
        seniority_keywords = ["senior", "lead", "principal", "staff", "manager", "sr"]
        junior_keywords = ["junior", "intern", "associate", "fresh", "entry", "jr"]
        
        job_is_senior = any(w in title for w in seniority_keywords)
        job_is_junior = any(w in title for w in junior_keywords)
        pref_is_senior = any(any(w in r for w in seniority_keywords) for r in self.preferred_roles)
        
        seniority_score = 5
        if pref_is_senior and job_is_senior:
            seniority_score = 10
        elif not pref_is_senior and not job_is_senior and not job_is_junior:
            seniority_score = 10
        elif not pref_is_senior and job_is_junior:
            seniority_score = 10

        # 5. Keyword Relevance (10%)
        relevance_keywords = ["remote", "immediately", "urgently", "bonus", "fulltime", "wfh", "hybrid"]
        relevance_matches = 0
        for kw in relevance_keywords:
            if kw in title or kw in description:
                relevance_matches += 1
        keyword_score = min(10, relevance_matches * 2)

        total_score = skills_score + role_score + location_score + seniority_score + keyword_score

        # Prioritization Boost for LinkedIn Posts
        if is_post:
            post_content = description
            boost_terms = ["hiring immediately", "urgently hiring", "remote", "open position", "referral", "recruiter contact"]
            boost_applied = False
            for term in boost_terms:
                if term in post_content:
                    total_score += 15
                    boost_applied = True
            if boost_applied:
                total_score = min(100, total_score)

        return min(100, total_score), matched_skills
