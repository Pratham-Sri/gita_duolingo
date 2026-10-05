"""
Database Schema for Gita Duolingo App
Supports SQLite, easily exportable to PostgreSQL / Supabase / Firebase.
"""

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

-- 1. Chapters
CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY,
    chapter_number INTEGER UNIQUE NOT NULL,
    name_sanskrit TEXT NOT NULL,
    name_transliterated TEXT NOT NULL,
    name_meaning TEXT NOT NULL,
    summary_en TEXT,
    summary_hi TEXT,
    verses_count INTEGER NOT NULL,
    slug TEXT
);

-- 2. Verses
CREATE TABLE IF NOT EXISTS verses (
    id INTEGER PRIMARY KEY,
    chapter_number INTEGER NOT NULL,
    verse_number INTEGER NOT NULL,
    verse_key TEXT UNIQUE NOT NULL, -- e.g. 'BG1.1'
    text_devanagari TEXT NOT NULL,
    transliteration TEXT NOT NULL,
    word_meanings_raw TEXT,
    translation_en TEXT NOT NULL,
    translation_hi TEXT,
    translation_source TEXT,
    speaker TEXT NOT NULL,
    commentary_summary TEXT,
    FOREIGN KEY(chapter_number) REFERENCES chapters(chapter_number)
);

CREATE INDEX IF NOT EXISTS idx_verses_chapter ON verses(chapter_number);
CREATE INDEX IF NOT EXISTS idx_verses_key ON verses(verse_key);

-- 3. Vocabulary breakdown (for Duolingo word bank & flashcards)
CREATE TABLE IF NOT EXISTS vocabulary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    verse_id INTEGER NOT NULL,
    verse_key TEXT NOT NULL,
    word_sanskrit TEXT NOT NULL,
    word_transliteration TEXT,
    meaning_en TEXT NOT NULL,
    FOREIGN KEY(verse_id) REFERENCES verses(id)
);

CREATE INDEX IF NOT EXISTS idx_vocab_verse ON vocabulary(verse_key);

-- 4. Duolingo-style Quiz Questions (10-20 per shloka)
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    verse_id INTEGER NOT NULL,
    verse_key TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    verse_number INTEGER NOT NULL,
    
    -- Duolingo Lesson Stage / Level:
    -- 1: Vocabulary & Words (Build roots)
    -- 2: Shloka Structure & Recitation (Grammar & Flow)
    -- 3: Meaning & Context (Comprehension)
    -- 4: Philosophy & Life Dilemmas (Application)
    lesson_level INTEGER NOT NULL DEFAULT 1,
    question_order INTEGER NOT NULL,
    
    -- Question Types:
    -- 'match_pairs', 'mcq_vocab', 'mcq_reverse_vocab', 'fill_blank', 
    -- 'word_order', 'speaker_context', 'translation_mcq', 
    -- 'philosophical_insight', 'life_scenario', 'true_false'
    question_type TEXT NOT NULL,
    difficulty TEXT NOT NULL CHECK(difficulty IN ('beginner', 'intermediate', 'advanced')),
    
    instruction TEXT NOT NULL,        -- e.g. "Select the correct meaning", "Fill in the blank"
    prompt TEXT NOT NULL,             -- The question prompt / sentence
    prompt_sanskrit TEXT,             -- Optional Sanskrit snippet
    
    options_json TEXT NOT NULL,       -- JSON Array of choices, or pair items
    correct_answer_json TEXT NOT NULL,-- Correct choice string, index, or match dict
    
    explanation TEXT NOT NULL,        -- Rich explanation with spiritual insight
    hint TEXT,                        -- Optional clue for learners
    xp_points INTEGER NOT NULL DEFAULT 10,
    
    FOREIGN KEY(verse_id) REFERENCES verses(id)
);

CREATE INDEX IF NOT EXISTS idx_questions_verse ON questions(verse_key);
CREATE INDEX IF NOT EXISTS idx_questions_type ON questions(question_type);
CREATE INDEX IF NOT EXISTS idx_questions_level ON questions(lesson_level);

-- 5. Duolingo Lesson Paths (Skill Tree structure)
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    verse_key TEXT NOT NULL,
    lesson_number INTEGER NOT NULL, -- 1 to 4
    title TEXT NOT NULL,
    description TEXT,
    total_xp INTEGER DEFAULT 50,
    FOREIGN KEY(verse_key) REFERENCES verses(verse_key)
);
"""
