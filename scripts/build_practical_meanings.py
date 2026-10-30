"""Draft distinct, modern-life PRACTICAL translations from verse-aligned Q&A."""

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / "cache" / "hf_english_qa.csv"
VERSE_DB = ROOT / "database" / "gita_duolingo.db"
OUT = ROOT / "data" / "practical_meanings.json"

SCENARIOS = {
    1: "a difficult family or community decision",
    2: "pressure to succeed at work or school",
    3: "doing necessary work without chasing recognition",
    4: "choosing responsible action during social change",
    5: "balancing personal ambition with care for others",
    6: "managing distraction and stress in daily routines",
    7: "responding thoughtfully to uncertainty",
    8: "keeping long-term values in mind during a crisis",
    9: "supporting others without seeking credit",
    10: "recognizing value and dignity in people around you",
    11: "facing consequences larger than one person's control",
    12: "practising patience and kindness in disagreement",
    13: "not reducing a person to appearance or status",
    14: "noticing how habits and moods shape decisions",
    15: "choosing lasting priorities over short-lived rewards",
    16: "resisting anger, arrogance, and harmful online behavior",
    17: "checking the intention behind a choice or sacrifice",
    18: "making a considered choice while honoring responsibilities",
}


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def main():
    qa = defaultdict(list)
    with QA.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            key = f"BG{row['chapter_no']}.{row['verse_no']}"
            qa[key].append(row)
    import sqlite3
    conn = sqlite3.connect(VERSE_DB)
    verses = conn.execute("select verse_key,chapter_number,translation_en from verses order by chapter_number,verse_number").fetchall()
    conn.close()

    result = {}
    for key, chapter, translation in verses:
        rows = qa.get(key, [])
        candidates = [r for r in rows if re.search(r"how can|everyday|daily life|apply|practice", r["question"], re.I)]
        if not candidates:
            candidates = rows
        if candidates:
            row = max(candidates, key=lambda r: sum(bool(re.search(p, r["question"], re.I)) for p in ("everyday", "daily life", "apply", "practice", "how", "what can", "lesson", "imply")))
            advice = clean(re.split(r"(?<=[.!?])\s+", row["answer"])[0])
            if advice and len(advice.split()) > 5:
                scenario = SCENARIOS.get(chapter, "a difficult everyday choice")
                practical = f"In a modern situation such as {scenario}, consider this application: {advice}"
                source = "Verse-aligned Q&A interpretation; application draft for editorial review"
            else:
                practical = ""
                source = ""
        else:
            practical = ""
            source = ""
        if not practical:
            # Preserve completeness but clearly mark unsupported items for authoring.
            practical = f"Apply the verse's teaching in a current situation involving {SCENARIOS.get(chapter, 'a difficult everyday choice')}. Author a verse-specific action step before publication."
            source = "Editorial placeholder; author a verse-specific modern-life application"
        result[key] = {"practical_meaning": practical, "source": source, "status": "editorial-review-required"}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verses": len(result), "review_required": len(result), "output": str(OUT)}, indent=2))


if __name__ == "__main__":
    main()
