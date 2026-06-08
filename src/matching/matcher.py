import re

class JobMatcher:
    def __init__(self, user_profile: dict):
        self.user_profile = user_profile
        self.user_skills = [s.lower() for s in user_profile.get("skills", [])]
        self.preferred_roles = [r.lower() for r in user_profile.get("preferred_roles", [])]
        self.preferred_locations = [l.lower() for l in user_profile.get("preferred_locations", [])]

    def calculate_score(self, job_or_post: dict, is_post: bool = False) -> tuple[int, list[str]]:
        """Calculate matching score between 0 and 100 and return matched skills.
        
        Attempts to use Gemini AI matching if GEMINI_API_KEY is set.
        Otherwise falls back to the Regex keyword matcher.
        """
        title = job_or_post.get("title", "").strip() if not is_post else "LinkedIn Post"
        description = job_or_post.get("description", "").strip() if not is_post else job_or_post.get("content", "").strip()
        location = job_or_post.get("location", "").strip() if not is_post else "Indonesia (Remote / Post)"

        from src.config.settings import settings
        if settings.GEMINI_API_KEY:
            try:
                import requests
                import json

                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={settings.GEMINI_API_KEY}"
                prompt = f"""
You are an expert HR recruiter assistant. Analyze the following job description or social media hiring post against the candidate's profile to check if it's relevant, is located in Indonesia or Remote, and calculate a match score.

Candidate Profile:
- Skills: {self.user_skills}
- Preferred Roles: {self.preferred_roles}
- Preferred Locations: {self.preferred_locations}

Job/Post Info:
- Title: {title}
- Description/Content: {description}
- Location: {location}

Respond with a JSON object containing exactly these fields:
- "is_relevant" (boolean): Is this job actually relevant to the candidate's preferred roles, seniorities, and location (Indonesia or Remote)? Return false if the post is from outside Indonesia, is spam, or is a user looking for a job instead of hiring.
- "score" (integer, 0 to 100): How well the candidate fits the job requirements.
- "matched_skills" (array of strings): Which of the candidate's skills are matched in the job requirements. Use strings matching the case of the candidate's profile skills.
- "reason" (string): A brief explanation (maximum 1 sentence) of the score or mismatch.
"""
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json"
                    }
                }
                res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    text_response = data["candidates"][0]["content"]["parts"][0]["text"]
                    result = json.loads(text_response)
                    
                    is_relevant = result.get("is_relevant", True)
                    if not is_relevant:
                        return 0, []
                    
                    score = int(result.get("score", 0))
                    matched_skills = result.get("matched_skills", [])
                    return min(100, max(0, score)), matched_skills
            except Exception as e:
                # Log warning and fallback silently to regex
                import logging
                logging.getLogger(__name__).warning(f"Gemini API matching failed: {e}. Falling back to Regex matcher.")

        # Fallback to Regex keyword matching
        title_lower = title.lower()
        description_lower = description.lower()
        location_lower = location.lower()

        # 1. Skills Match (50%)
        matched_skills = []
        for skill in self.user_skills:
            escaped_skill = re.escape(skill)
            if any(char in skill for char in ["+", "#", ".", "/"]):
                pattern = rf"(?:^|[\s/,\-\(\)])({escaped_skill})(?:$|[\s/,\-\(\)])"
            else:
                pattern = rf"\b{escaped_skill}\b"
                
            if re.search(pattern, title_lower) or re.search(pattern, description_lower):
                orig_skill = next((s for s in self.user_profile.get("skills", []) if s.lower() == skill), skill)
                matched_skills.append(orig_skill)

        skills_ratio = len(matched_skills) / max(1, len(self.user_skills))
        skills_score = int(skills_ratio * 50)

        # 2. Role Match (20%)
        role_score = 0
        text_to_check = title_lower if not is_post else description_lower
        for role in self.preferred_roles:
            if role in text_to_check:
                role_score = 20
                break

        # 3. Location Match (10%)
        location_score = 0
        for loc in self.preferred_locations:
            if loc in location_lower or (loc == "remote" and ("remote" in title_lower or "remote" in description_lower)):
                location_score = 10
                break

        # 4. Seniority Match (10%)
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

        # 5. Keyword Relevance (10%)
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

        return min(100, total_score), matched_skills
