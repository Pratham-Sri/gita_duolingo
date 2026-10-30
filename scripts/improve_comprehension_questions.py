"""Replace Sanskrit recall drills with English shloka-comprehension questions.

The script edits each existing question row in place, preserving the exact
number of questions per verse while grounding every correct answer in that
verse's English translation.
"""

import json
import random
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "gita_duolingo.db"
SEED = ROOT / "exports" / "prisma_seed_content.json"

STEMS = [
    "Which choice best expresses the main point of this shloka?",
    "What is the verse saying about the situation it describes?",
    "Which interpretation is most faithful to the verse?",
    "What idea should a reader take from this verse?",
    "Which statement accurately captures the verse's message?",
    "What does this verse ask the reader to understand?",
    "Which summary preserves the meaning of the shloka?",
    "What is the central teaching expressed here?",
    "Which reading is supported by the verse?",
    "What does the verse describe or teach?",
    "Which option best reflects the meaning in context?",
    "What is the most accurate way to understand this verse?",
    "Which statement stays closest to the verse's message?",
    "What should a reader understand from this shloka?",
]

WORD_RE = re.compile(r"[a-z][a-z'-]{2,}")
STOP = set("the and for that this with from have will your when what which into about their them then than they were was are its his her you all not but who how does only each through against upon".split())


def terms(text):
    return {w for w in WORD_RE.findall((text or "").lower()) if w not in STOP}


def meaning_units(text):
    """Split a translation into readable claims without inventing paraphrases."""
    text = re.sub(r"^\s*\d+\.\d+\s+", "", (text or "").strip())
    units = []
    for sentence in re.split(r"(?<=[.!?])\s+|[;]", text):
        pieces = re.split(r",\s+|\s+(?:but|while|whereas|and)\s+", sentence)
        units.extend(piece.strip(" \"'.,;:") for piece in pieces if len(piece.split()) >= 3)
    # Avoid highly fragmentary answers; a whole sentence is better than a fragment.
    return list(dict.fromkeys(units)) or ([text] if text else [])


def make_options(target, verse_key, candidates):
    target_terms = terms(target)
    target_len = len(target.split())
    ranked = []
    for row in candidates:
        text = (row["translation_en"] or "").strip()
        if not text or row["verse_key"] == verse_key:
            continue
        for unit in meaning_units(text):
            length = len(unit.split())
            if not target_terms or not 0.5 * target_len <= length <= 1.8 * max(target_len, 1):
                continue
            other_terms = terms(unit)
            overlap = len(target_terms & other_terms) / max(1, len(target_terms | other_terms))
            ranked.append((overlap, -abs(length - target_len), unit))
    ranked.sort(reverse=True)
    pool = list(dict.fromkeys(item[2] for item in ranked[:30]))
    if len(pool) < 3:
        pool.extend(
            row["translation_en"].strip() for row in candidates
            if row["verse_key"] != verse_key and row["translation_en"]
            and row["translation_en"].strip().casefold() != target.casefold()
        )
    pool = list(dict.fromkeys(pool))
    rng = random.Random(verse_key + ":" + target)
    distractors = rng.sample(pool, min(3, len(pool)))
    options = [target, *distractors]
    while len(options) < 4:
        options.append("The verse gives no guidance about the situation or idea it describes.")
    rng.shuffle(options)
    return options[:4]


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    verses = [dict(r) for r in conn.execute(
        "SELECT verse_key, chapter_number, verse_number, translation_en, meaning_en "
        "FROM verses ORDER BY chapter_number, verse_number"
    )]
    by_key = {r["verse_key"]: r for r in verses}
    questions = [dict(r) for r in conn.execute(
        "SELECT * FROM questions ORDER BY verse_key, question_order, id"
    )]
    by_chapter = defaultdict(list)
    for verse in verses:
        by_chapter[verse["chapter_number"]].append(verse)

    before_counts = Counter(q["verse_key"] for q in questions)
    for q in questions:
        verse = by_key[q["verse_key"]]
        full_meaning = (verse["translation_en"] or "").strip()
        units = meaning_units(full_meaning)
        if not units:
            # Preserve the row if the source has no usable English meaning.
            continue
        order = q["question_order"]
        target = units[(order - 1) % len(units)]
        options = make_options(target, q["verse_key"], by_chapter[verse["chapter_number"]])
        prompt = STEMS[(order - 1) % len(STEMS)]
        answer = target
        conn.execute(
            """UPDATE questions SET lesson_level = 3, question_type = 'translation_mcq',
               difficulty = ?, instruction = 'Choose the best interpretation', prompt = ?,
               prompt_sanskrit = NULL, options_json = ?, correct_answer_json = ?,
               explanation = ?, hint = NULL WHERE id = ?""",
            (
                "intermediate" if order % 3 else "advanced", prompt,
                json.dumps(options, ensure_ascii=False),
                json.dumps(answer, ensure_ascii=False),
                f"This detail is stated in the verse's English translation: {target}",
                q["id"],
            ),
        )
    conn.commit()
    after_counts = Counter(r[0] for r in conn.execute(
        "SELECT verse_key FROM questions"
    ))
    total = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    conn.close()
    if before_counts != after_counts:
        raise RuntimeError("Question counts per verse changed unexpectedly.")
    sync_seed()
    print(json.dumps({
        "questions_preserved": total,
        "verses_with_questions": len(before_counts),
        "question_types": {"translation_mcq": total},
        "per_verse_question_counts_preserved": True,
    }, indent=2))


def sync_seed():
    """Update quiz rows/options in the app seed without changing unrelated timestamps."""
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    db_questions = {
        row["id"]: dict(row) for row in conn.execute("SELECT * FROM questions")
    }
    conn.close()
    seed_questions = seed["records"]["quizQuestions"]
    seed_options = seed["records"]["quizOptions"]
    changed_ids = set()
    for item in seed_questions:
        source_id = item.get("sourceQuestionId")
        row = db_questions.get(source_id)
        if row is None:
            continue
        options = json.loads(row["options_json"])
        answer = json.loads(row["correct_answer_json"])
        item.update({
            "type": "SINGLE_CHOICE", "question": row["prompt"],
            "explanation": row["explanation"], "points": row["xp_points"],
            "questionType": row["question_type"], "lessonLevel": row["lesson_level"],
            "instruction": row["instruction"], "sourceQuestionOrder": row["question_order"],
            "difficulty": row["difficulty"], "promptSanskrit": None, "hint": None,
            "answerOptions": options,
            "correctAnswer": answer,
        })
        changed_ids.add(item["id"])
    seed_options[:] = [item for item in seed_options if item["questionId"] not in changed_ids]
    for question in seed_questions:
        if question["id"] not in changed_ids:
            continue
        for order, value in enumerate(question["answerOptions"], start=1):
            seed_options.append({
                "id": __import__("hashlib").sha256(
                    f"gitalingo:quiz_option:verse-question:{question['sourceQuestionId']}:{order}".encode()
                ).hexdigest()[:24],
                "questionId": question["id"], "value": value, "label": value,
                "isCorrect": value.strip().casefold() == question["correctAnswer"].strip().casefold(),
                "explanation": None, "order": order,
            })
    SEED.write_text(json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
