-- Create jobs table
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    company VARCHAR(255) NOT NULL,
    location VARCHAR(255),
    description TEXT,
    url TEXT UNIQUE NOT NULL,
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create user_profile table
CREATE TABLE IF NOT EXISTS user_profile (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skills TEXT[] NOT NULL,
    preferred_roles TEXT[] NOT NULL,
    preferred_locations TEXT[] NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create job_matches table
CREATE TABLE IF NOT EXISTS job_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    score INT NOT NULL,
    matched_skills TEXT[] NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create linkedin_posts table
CREATE TABLE IF NOT EXISTS linkedin_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    author_name VARCHAR(255),
    author_profile_url TEXT,
    company VARCHAR(255),
    content TEXT NOT NULL,
    post_url TEXT UNIQUE NOT NULL,
    posted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create job_sources table
CREATE TABLE IF NOT EXISTS job_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name VARCHAR(100) UNIQUE NOT NULL,
    last_scraped_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) NOT NULL
);

-- Seed user profile
INSERT INTO user_profile (skills, preferred_roles, preferred_locations)
VALUES (
    ARRAY['Python', 'Docker', 'React', 'AWS', 'PostgreSQL', 'CI/CD', 'Git', 'Playwright', 'FastAPI'],
    ARRAY['Backend Engineer', 'Software Engineer', 'Fullstack Developer'],
    ARRAY['Jakarta', 'Remote', 'Tangerang', 'Indonesia']
) ON CONFLICT DO NOTHING;

-- Seed job sources
INSERT INTO job_sources (source_name, status)
VALUES 
    ('LinkedIn Jobs', 'PENDING'),
    ('LinkedIn Posts', 'PENDING'),
    ('Indeed', 'PENDING'),
    ('JobStreet', 'PENDING'),
    ('Glints', 'PENDING'),
    ('Kalibrr', 'PENDING')
ON CONFLICT (source_name) DO NOTHING;
