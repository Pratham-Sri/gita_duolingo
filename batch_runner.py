"""
Batch Runner for Gita Duolingo DB
Fetches verses from RapidAPI and populates the SQLite database with 14-18 questions per shloka.
"""

import sys
import io
import time
import json
import sqlite3
import argparse
from generator import (
    init_db, fetch_chapters, fetch_verse,
    generate_questions_for_verse, save_verse_and_questions_to_db,
    export_json_summaries, get_db_connection, DB_PATH
)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def run_batch(chapter_num: int, start_verse: int = 1, end_verse: int = None, delay: float = 0.5):
    print(f"=== Gita Duolingo DB Batch Generator ===")
    print(f"Chapter: {chapter_num}, Starting from Verse {start_verse}")
    
    init_db()
    chapters = fetch_chapters()
    target_ch = next((c for c in chapters if c.get("chapter_number") == chapter_num), None)
    if not target_ch:
        print(f"Chapter {chapter_num} not found!")
        return

    # Save chapter info to DB
    conn = get_db_connection()
    for ch in chapters:
        conn.execute("""
            INSERT OR REPLACE INTO chapters (
                id, chapter_number, name_sanskrit, name_transliterated,
                name_meaning, summary_en, summary_hi, verses_count, slug
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ch.get("id"), ch.get("chapter_number"), ch.get("name"),
            ch.get("name_transliterated"), ch.get("name_meaning"),
            ch.get("chapter_summary"), ch.get("chapter_summary_hindi"),
            ch.get("verses_count"), ch.get("slug")
        ))
    conn.commit()
    conn.close()

    total_in_ch = target_ch.get("verses_count", 47)
    if end_verse is None or end_verse > total_in_ch:
        end_verse = total_in_ch

    print(f"Generating questions for Chapter {chapter_num} ({target_ch.get('name_transliterated')}): verses {start_verse} to {end_verse}...")
    
    generated_count = 0
    total_q = 0
    
    for v_num in range(start_verse, end_verse + 1):
        try:
            print(f"[{v_num}/{end_verse}] Fetching BG {chapter_num}.{v_num}...", end="", flush=True)
            v_data = fetch_verse(chapter_num, v_num)
            questions = generate_questions_for_verse(v_data, target_ch)
            save_verse_and_questions_to_db(v_data, target_ch, questions)
            total_q += len(questions)
            generated_count += 1
            print(f" Done! (+{len(questions)} questions)")
            if delay > 0:
                time.sleep(delay)
        except Exception as e:
            print(f"\n[ERROR] Failed on verse {chapter_num}.{v_num}: {e}")
            continue

    export_json_summaries()
    print(f"\n=== Completed Batch ===")
    print(f"Verses Processed: {generated_count}")
    print(f"Questions Generated: {total_q}")
    print(f"Database Location: {DB_PATH}")

def run_all_missing(batch_size: int = 25, delay: float = 0.2):
    """Fetch missing verses in resumable chapter-sized batches."""
    init_db()
    chapters = fetch_chapters()
    conn = get_db_connection()
    existing = {row[0] for row in conn.execute("SELECT verse_key FROM verses")}
    conn.close()

    for chapter in chapters:
        chapter_num = chapter.get("chapter_number")
        verse_count = chapter.get("verses_count", 0)
        missing = [v for v in range(1, verse_count + 1)
                   if f"BG{chapter_num}.{v}" not in existing]
        for offset in range(0, len(missing), batch_size):
            batch = missing[offset:offset + batch_size]
            print(f"=== Chapter {chapter_num}: batch {offset // batch_size + 1}, "
                  f"verses {batch[0]}-{batch[-1]} ({len(batch)} verses) ===")
            run_batch(chapter_num, batch[0], batch[-1], delay)
            existing.update(f"BG{chapter_num}.{v}" for v in batch)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Gita Quiz Questions DB")
    parser.add_argument("--chapter", type=int, default=1, help="Chapter number (1-18)")
    parser.add_argument("--start", type=int, default=1, help="Start verse number")
    parser.add_argument("--end", type=int, default=15, help="End verse number")
    parser.add_argument("--delay", type=float, default=0.2, help="Delay between API calls in seconds")
    parser.add_argument("--all-missing", action="store_true", help="Fetch every verse not already in the database")
    parser.add_argument("--batch-size", type=int, default=25, help="Verse count per resumable batch when using --all-missing")
    args = parser.parse_args()

    if args.all_missing:
        run_all_missing(batch_size=args.batch_size, delay=args.delay)
    else:
        run_batch(chapter_num=args.chapter, start_verse=args.start, end_verse=args.end, delay=args.delay)
