"""
Export Utility for Gita Duolingo DB
Generates SQL dump and clean JSON files for mobile apps (Flutter, React Native, Swift, Kotlin)
and backend databases (PostgreSQL, Supabase, Firebase).
"""

import os
import json
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "database", "gita_duolingo.db")
EXPORTS_DIR = os.path.join(BASE_DIR, "exports")
os.makedirs(EXPORTS_DIR, exist_ok=True)

def export_all():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # 0. Thematic course for applications that organize lessons by concept.
    curriculum_source = os.path.join(BASE_DIR, "data", "curriculum.json")
    curriculum_export = os.path.join(EXPORTS_DIR, "curriculum.json")
    with open(curriculum_source, "r", encoding="utf-8") as source, \
            open(curriculum_export, "w", encoding="utf-8") as target:
        json.dump(json.load(source), target, ensure_ascii=False, indent=2)
    print(f"[JSON] Exported thematic curriculum: {curriculum_export}")

    # 1. SQL Dump
    sql_path = os.path.join(EXPORTS_DIR, "gita_duolingo.sql")
    with open(sql_path, "w", encoding="utf-8") as f:
        for line in conn.iterdump():
            f.write(f"{line}\n")
    print(f"[SQL] Generated SQL dump: {sql_path}")

    # 2. Chapters JSON
    chapters = [dict(r) for r in c.execute("SELECT * FROM chapters ORDER BY chapter_number").fetchall()]
    with open(os.path.join(EXPORTS_DIR, "chapters.json"), "w", encoding="utf-8") as f:
        json.dump(chapters, f, ensure_ascii=False, indent=2)

    # 3. Verses JSON
    verses = []
    for row in c.execute("SELECT * FROM verses ORDER BY chapter_number, verse_number").fetchall():
        verse = dict(row)
        verse["meaning"] = verse.get("meaning_en")
        verses.append(verse)
    with open(os.path.join(EXPORTS_DIR, "verses.json"), "w", encoding="utf-8") as f:
        json.dump(verses, f, ensure_ascii=False, indent=2)

    # 4. Questions JSON
    questions_raw = [dict(r) for r in c.execute("SELECT * FROM questions ORDER BY chapter_number, verse_number, question_order").fetchall()]
    questions = []
    for q in questions_raw:
        q_clean = dict(q)
        q_clean["options"] = json.loads(q["options_json"])
        q_clean["correct_answer"] = json.loads(q["correct_answer_json"])
        del q_clean["options_json"]
        del q_clean["correct_answer_json"]
        questions.append(q_clean)

    with open(os.path.join(EXPORTS_DIR, "questions.json"), "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

    # 5. Duolingo Bundle (Grouped by verse key for easy offline mobile caching)
    bundle = {}
    for v in verses:
        v_key = v["verse_key"]
        v_questions = [q for q in questions if q["verse_key"] == v_key]
        bundle[v_key] = {
            "verse": v,
            "questions_count": len(v_questions),
            "questions": v_questions
        }

    with open(os.path.join(EXPORTS_DIR, "gita_duolingo_bundle.json"), "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)

    print(f"[JSON] Exported {len(chapters)} chapters, {len(verses)} verses, {len(questions)} questions to {EXPORTS_DIR}")
    conn.close()

if __name__ == "__main__":
    export_all()
