import re

class JobMatcher:
    def __init__(self, user_profile: dict):
        self.user_profile = user_profile
        self.user_skills = [s.lower() for s in user_profile.get("skills", [])]
        self.preferred_roles = [r.lower() for r in user_profile.get("preferred_roles", [])]
        self.preferred_locations = [l.lower() for l in user_profile.get("preferred_locations", [])]

    def calculate_score(self, job_or_post: dict, is_post: bool = False) -> tuple[int, list[str]]:
        """Calculate matching score between 0 and 100 and return matched skills.
        
        Scoring Breakdown:
        - Skills match (50%)
        - Role match (20%)
        - Location match (10%)
        - Seniority match (10%)
        - Keyword relevance (10%)
        
        LinkedIn Posts:
        - Prioritization boost if contains hiring key phrases.
        """
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
