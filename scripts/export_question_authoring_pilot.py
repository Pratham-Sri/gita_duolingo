"""Create a spreadsheet-friendly review file from the authored pilot bank."""

import csv
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "data" / "question_authoring_pilot.json"
DB = ROOT / "database" / "gita_duolingo.db"
OUT = ROOT / "exports" / "question_authoring_pilot.csv"


def main():
    payload = json.loads(PILOT.read_text(encoding="utf-8"))
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    verses = {r["verse_key"]: dict(r) for r in conn.execute(
        "SELECT verse_key, chapter_number, verse_number, text_devanagari, transliteration FROM verses"
    )}
    conn.close()
    fields = ["status", "question_id", "verse_key", "chapter", "verse", "concept",
              "prerequisite_verse", "sanskrit", "transliteration", "question_type", "skill",
              "difficulty", "prompt", "source_translation", "option_a", "option_b", "option_c", "option_d",
              "correct_answer", "explanation", "source", "editor_notes"]
    with OUT.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for q in payload["questions"]:
            verse = verses[q["verse_key"]]
            chapter, number = verse["chapter_number"], verse["verse_number"]
            cache = json.loads((ROOT / "cache" / "verses" / f"ch_{chapter}_v_{number}.json").read_text(encoding="utf-8"))
            source = next(t for t in cache["translations"] if t.get("author") == "Shri Purohit Swami")
            translation = re.sub(r"^\s*\d+\.\d+\s*", "", source["description"]).strip()
            writer.writerow({
                "status": "Expert review required", "question_id": q["id"],
                "verse_key": q["verse_key"], "chapter": verse["chapter_number"],
                "verse": verse["verse_number"], "concept": q["concept"],
                "prerequisite_verse": q["prerequisite_verse"],
                "sanskrit": verse["text_devanagari"], "transliteration": verse["transliteration"],
                "question_type": q["question_type"], "skill": q["skill"],
                "difficulty": q["difficulty"], "prompt": q["prompt"],
                "source_translation": translation,
                **{f"option_{chr(97+i)}": option for i, option in enumerate(q["options"])},
                "correct_answer": q["correct_answer"], "explanation": q["explanation"],
                "source": q["source"], "editor_notes": q["editor_notes"],
            })
    print(f"Exported {len(payload['questions'])} review questions to {OUT}")


if __name__ == "__main__":
    main()
