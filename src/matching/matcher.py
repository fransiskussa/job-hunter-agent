import re

class JobMatcher:
    def __init__(self, user_profile: dict):
        self.user_profile = user_profile
        self.user_skills = [s.lower() for s in user_profile.get("skills", [])]
        self.preferred_roles = [r.lower() for r in user_profile.get("preferred_roles", [])]
        self.preferred_locations = [l.lower() for l in user_profile.get("preferred_locations", [])]

    def calculate_score(self, job_or_post: dict, is_post: bool = False) -> tuple[int, list[str]]:
        """Calculate matching score between 0 and 100 and return matched skills using regex matches."""
        title = job_or_post.get("title", "").strip() if not is_post else "LinkedIn Post"
        description = job_or_post.get("description", "").strip() if not is_post else job_or_post.get("content", "").strip()
        location = job_or_post.get("location", "").strip() if not is_post else "Indonesia (Remote / Post)"

        title_lower = title.lower()
        description_lower = description.lower()
        location_lower = location.lower()

        # === 1. PRE-FILTERING & SKILLS MATCHING (Lokal & Cepat) ===
        # Pencocokan Skill dasar
        regex_matched_skills = []
        for skill in self.user_skills:
            escaped_skill = re.escape(skill)
            if any(char in skill for char in ["+", "#", ".", "/"]):
                pattern = rf"(?:^|[\s/,\-\(\)])({escaped_skill})(?:$|[\s/,\-\(\)])"
            else:
                pattern = rf"\b{escaped_skill}\b"
                
            if re.search(pattern, title_lower) or re.search(pattern, description_lower):
                orig_skill = next((s for s in self.user_profile.get("skills", []) if s.lower() == skill), skill)
                regex_matched_skills.append(orig_skill)

        # Pencocokan Role dasar
        has_role_match = False
        text_to_check = title_lower if not is_post else description_lower
        for role in self.preferred_roles:
            if role in text_to_check:
                has_role_match = True
                break

        # Jika TIDAK ADA skill DAN TIDAK ADA preferred role yang cocok sama sekali, langsung kembalikan 0.
        if not regex_matched_skills and not has_role_match:
            return 0, []

        # === 2. REGEX MATCHING SCORING ===
        skills_ratio = len(regex_matched_skills) / max(1, len(self.user_skills))
        skills_score = int(skills_ratio * 50)

        # Role Match (20%)
        role_score = 20 if has_role_match else 0

        # Location Match (10%)
        location_score = 0
        for loc in self.preferred_locations:
            if loc in location_lower or (loc == "remote" and ("remote" in title_lower or "remote" in description_lower)):
                location_score = 10
                break

        # Seniority Match (10%)
        seniority_keywords = ["senior", "lead", "principal", "staff", "manager", "sr"]
        junior_keywords = ["junior", "intern", "associate", "fresh", "entry", "jr"]
        
        job_is_senior = any(w in title_lower for w in seniority_keywords)
        job_is_junior = any(w in title_lower for w in junior_keywords)
        pref_is_senior = any(any(w in r for w in seniority_keywords) for r in self.preferred_roles)
        
        seniority_score = 5
        if pref_is_senior and job_is_senior:
            seniority_score = 10
        elif not pref_is_senior and not job_is_senior and not job_is_junior:
            seniority_score = 10
        elif not pref_is_senior and job_is_junior:
            seniority_score = 10

        # Keyword Relevance (10%)
        relevance_keywords = ["remote", "immediately", "urgently", "bonus", "fulltime", "wfh", "hybrid"]
        relevance_matches = 0
        for kw in relevance_keywords:
            if kw in title_lower or kw in description_lower:
                relevance_matches += 1
        keyword_score = min(10, relevance_matches * 2)

        total_score = skills_score + role_score + location_score + seniority_score + keyword_score

        # Prioritization Boost for LinkedIn Posts
        if is_post:
            post_content = description_lower
            boost_terms = ["hiring immediately", "urgently hiring", "remote", "open position", "referral", "recruiter contact"]
            boost_applied = False
            for term in boost_terms:
                if term in post_content:
                    total_score += 15
                    boost_applied = True
            if boost_applied:
                total_score = min(100, total_score)

        return min(100, total_score), regex_matched_skills
