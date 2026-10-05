"""Fill missing verse meanings with 50-60 word contextual explanations."""

import json
import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))

from gitalingo.generator import BASE_DIR, DB_PATH, generate_verse_meaning, init_db
from export_db import export_all

OVERRIDES_PATH = os.path.join(BASE_DIR, "data", "translation_overrides.json")

def valid_translation(candidate: str) -> bool:
    normalized = (candidate or "").strip().lower()
    return bool(normalized) and not any(marker in normalized for marker in (
        "did not comment", "no changes needed", "translation not available"
    ))


def generate_all_meanings(batch_size: int = 50) -> None:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if os.path.exists(OVERRIDES_PATH):
        with open(OVERRIDES_PATH, "r", encoding="utf-8") as override_file:
            overrides = json.load(override_file)
    else:
        overrides = {}
    verses = conn.execute("""
        SELECT v.*, c.name_meaning, c.summary_en
        FROM verses v JOIN chapters c USING (chapter_number)
        ORDER BY v.chapter_number, v.verse_number
    """).fetchall()

    pending = []
    updated = 0
    for row in verses:
        verse = dict(row)
        verse_key = verse["verse_key"]
        translation_source = verse.get("translation_source")
        translation = verse.get("translation_en") or ""

        override = overrides.get(verse["verse_key"])
        if override:
            translation = override["translation_en"]
            translation_source = override["translation_source"]

        # Restore the source text before regenerating entries previously filled
        # by this script, so the meaning never gets summarized recursively.
        if translation_source == "Generated from Sanskrit word meanings and chapter context":
            ch_num, v_num = verse["chapter_number"], verse["verse_number"]
            cache_path = os.path.join(BASE_DIR, "cache", "verses", f"ch_{ch_num}_v_{v_num}.json")
            if os.path.exists(cache_path):
                with open(cache_path, "r", encoding="utf-8") as cache_file:
                    cached = json.load(cache_file)
                original = next((item for item in cached.get("translations", [])
                                 if item.get("language") == "english"), None)
                translation = original.get("description", "") if original else ""

        # Chapter 1, verse 7 has a bad provider placeholder but a valid
        # alternate translation in the original cache.
        if not valid_translation(translation):
            ch_num, v_num = verse["chapter_number"], verse["verse_number"]
            cache_path = os.path.join(BASE_DIR, "cache", "verses", f"ch_{ch_num}_v_{v_num}.json")
            if os.path.exists(cache_path):
                with open(cache_path, "r", encoding="utf-8") as cache_file:
                    cached = json.load(cache_file)
                alternate = next((item for item in cached.get("translations", [])
                                  if valid_translation(item.get("description", ""))), None)
                if alternate:
                    translation = alternate["description"].strip()
                    translation_source = (alternate.get("author_name") or alternate.get("author")
                                          or "Alternate cached English translation")

        verse["translation_en"] = translation
        meaning = generate_verse_meaning(verse, verse)
        if not valid_translation(translation):
            # Preserve a useful English explanation in both common meaning
            # fields instead of leaving provider commentary placeholders.
            translation = meaning
            translation_source = "Generated from Sanskrit word meanings and chapter context"

        pending.append((meaning, translation, translation_source, verse_key))
        if len(pending) >= batch_size:
            conn.executemany("""
                UPDATE verses SET meaning_en = ?, translation_en = ?, translation_source = ?
                WHERE verse_key = ?
            """, pending)
            conn.commit()
            updated += len(pending)
            print(f"Saved meanings for {updated}/{len(verses)} verses")
            pending.clear()

    if pending:
        conn.executemany("""
            UPDATE verses SET meaning_en = ?, translation_en = ?, translation_source = ?
            WHERE verse_key = ?
        """, pending)
        conn.commit()
        updated += len(pending)
    remaining = conn.execute("""
        SELECT count(*) FROM verses
        WHERE meaning_en IS NULL OR trim(meaning_en) = ''
           OR length(meaning_en) = 0
    """).fetchone()[0]
    conn.close()

    if remaining:
        raise RuntimeError(f"{remaining} verses still have no generated meaning")
    print(f"Generated meanings for {updated} verses; refreshing exports.")
    export_all()


if __name__ == "__main__":
    generate_all_meanings()
