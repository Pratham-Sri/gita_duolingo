"""
FastAPI Server for Gita Duolingo Quiz DB
Provides REST API endpoints and serves an interactive Duolingo-style learning interface.
"""

import os
import json
import sqlite3
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gita_duolingo.db")
WEB_DIR = os.path.join(BASE_DIR, "web")
CURRICULUM_PATH = os.path.join(BASE_DIR, "data", "curriculum.json")
os.makedirs(WEB_DIR, exist_ok=True)

with open(CURRICULUM_PATH, "r", encoding="utf-8") as curriculum_file:
    CURRICULUM = json.load(curriculum_file)

app = FastAPI(
    title="Gita Duolingo Quiz API",
    description="Interactive Sanskrit & Bhagavad Gita learning database and quiz engine.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/api/stats")
def get_stats():
    conn = get_db()
    c = conn.cursor()
    ch_count = c.execute("SELECT count(*) as c FROM chapters").fetchone()["c"]
    v_count = c.execute("SELECT count(*) as c FROM verses").fetchone()["c"]
    q_count = c.execute("SELECT count(*) as c FROM questions").fetchone()["c"]
    vocab_count = c.execute("SELECT count(*) as c FROM vocabulary").fetchone()["c"]
    conn.close()
    return {
        "chapters_count": ch_count,
        "verses_count": v_count,
        "questions_count": q_count,
        "vocabulary_count": vocab_count
    }

@app.get("/api/chapters")
def get_chapters():
    conn = get_db()
    rows = conn.execute("SELECT * FROM chapters ORDER BY chapter_number").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/curriculum")
def get_curriculum():
    """Return the portable, theme-based course structure and its questions."""
    return CURRICULUM

@app.get("/api/sections")
def get_sections():
    """Return the ordered learning sections without their question payloads."""
    return [{k: v for k, v in section.items() if k != "questions"}
            for section in CURRICULUM["sections"]]

@app.get("/api/sections/{section_id}")
def get_section(section_id: str):
    """Return one section with its lesson questions for an external client."""
    section = next((s for s in CURRICULUM["sections"] if s["id"] == section_id), None)
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found")
    return section

@app.get("/api/chapters/{chapter_number}/verses")
def get_chapter_verses(chapter_number: int):
    conn = get_db()
    rows = conn.execute("""
        SELECT id, chapter_number, verse_number, verse_key, text_devanagari,
               transliteration, translation_en, meaning_en, meaning_en AS meaning,
               translation_source, speaker
        FROM verses
        WHERE chapter_number = ?
        ORDER BY verse_number
    """, (chapter_number,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/verses/{verse_key}")
def get_verse(verse_key: str):
    conn = get_db()
    v = conn.execute("SELECT * FROM verses WHERE verse_key = ?", (verse_key,)).fetchone()
    if not v:
        conn.close()
        raise HTTPException(status_code=404, detail="Verse not found")
    
    vocab = conn.execute("SELECT * FROM vocabulary WHERE verse_key = ?", (verse_key,)).fetchall()
    conn.close()
    
    res = dict(v)
    res["meaning"] = res.get("meaning_en")
    res["vocabulary"] = [dict(r) for r in vocab]
    return res

@app.get("/api/verses/{verse_key}/quiz")
def get_verse_quiz(verse_key: str, level: Optional[int] = None):
    conn = get_db()
    query = "SELECT * FROM questions WHERE verse_key = ?"
    params = [verse_key]
    if level is not None:
        query += " AND lesson_level = ?"
        params.append(level)
    query += " ORDER BY question_order"
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    results = []
    for r in rows:
        d = dict(r)
        d["options"] = json.loads(d["options_json"])
        d["correct_answer"] = json.loads(d["correct_answer_json"])
        del d["options_json"]
        del d["correct_answer_json"]
        results.append(d)
        
    return {
        "verse_key": verse_key,
        "total_questions": len(results),
        "questions": results
    }

class QuizAnswerSubmission(BaseModel):
    question_id: int
    user_answer: Any

@app.post("/api/quiz/validate")
def validate_answer(sub: QuizAnswerSubmission):
    conn = get_db()
    q = conn.execute("SELECT * FROM questions WHERE id = ?", (sub.question_id,)).fetchone()
    conn.close()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
        
    correct = json.loads(q["correct_answer_json"])
    is_correct = False
    
    if q["question_type"] == "match_pairs":
        # sub.user_answer is a dict of pairs
        is_correct = (sub.user_answer == correct)
    elif q["question_type"] == "word_order":
        is_correct = (sub.user_answer == correct)
    else:
        is_correct = str(sub.user_answer).strip().lower() == str(correct).strip().lower()
        
    return {
        "is_correct": is_correct,
        "correct_answer": correct,
        "explanation": q["explanation"],
        "xp_earned": q["xp_points"] if is_correct else 0
    }

@app.get("/", response_class=HTMLResponse)
def index():
    html_path = os.path.join(WEB_DIR, "index.html")
    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>Gita Duolingo Server Running</h1><p>Visit /docs for API documentation.</p>"

if __name__ == "__main__":
    import uvicorn
    print("[API] Starting server on http://127.0.0.1:8000 ...")
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)
