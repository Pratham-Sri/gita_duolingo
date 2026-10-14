"""Separate Sanskrit Devanagari, Roman transliteration, and English gloss fields."""

import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gitalingo.transliteration import normalize_sanskrit_word

DB_PATH = ROOT / "database" / "gita_duolingo.db"


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    words = [dict(row) for row in conn.execute(
        "SELECT id, word_sanskrit, word_transliteration FROM vocabulary ORDER BY id"
    )]
    transformed = []
    invalid_ids = []
    for row in words:
        devanagari, roman = normalize_sanskrit_word(row["word_sanskrit"])
        if not any("\u0900" <= char <= "\u097f" for char in devanagari):
            invalid_ids.append((row["id"],))
            continue
        transformed.append((devanagari, row["word_transliteration"] or roman, row["id"]))

    conn.execute("BEGIN")
    conn.executemany(
        "UPDATE vocabulary SET word_sanskrit = ?, word_transliteration = ? WHERE id = ?",
        transformed,
    )
    conn.executemany("DELETE FROM vocabulary WHERE id = ?", invalid_ids)

    questions = conn.execute(
        "SELECT id, question_type, prompt, prompt_sanskrit, explanation, options_json, correct_answer_json "
        "FROM questions WHERE question_type IN ('match_pairs', 'mcq_vocab', 'mcq_reverse_vocab')"
    ).fetchall()
    for question in questions:
        prompt = question["prompt"]
        prompt_sanskrit = question["prompt_sanskrit"]
        explanation = question["explanation"]
        options = json.loads(question["options_json"])
        answer = json.loads(question["correct_answer_json"])

        if question["question_type"] == "match_pairs" and isinstance(options, dict):
            options["words"] = [normalize_sanskrit_word(word)[0] for word in options.get("words", [])]
            if isinstance(answer, dict):
                answer = {normalize_sanskrit_word(word)[0]: meaning for word, meaning in answer.items()}
        elif question["question_type"] == "mcq_vocab":
            old_word = prompt_sanskrit or ""
            new_word = normalize_sanskrit_word(old_word)[0]
            prompt_sanskrit = new_word
            if old_word:
                pattern = rf"(?<!\w){re.escape(old_word)}(?!\w)"
                prompt = re.sub(pattern, lambda _match: new_word, prompt, flags=re.IGNORECASE)
                explanation = re.sub(pattern, lambda _match: new_word, explanation, flags=re.IGNORECASE)
        elif question["question_type"] == "mcq_reverse_vocab":
            if isinstance(options, list):
                options = [normalize_sanskrit_word(value)[0] for value in options]
            if isinstance(answer, str):
                answer = normalize_sanskrit_word(answer)[0]
            # The explanation repeats the correct transliteration.
            match = re.search(r'"(.+?)"', explanation)
            if match:
                old_word = match.group(1)
                new_word = normalize_sanskrit_word(old_word)[0]
                explanation = explanation[:match.start(1)] + new_word + explanation[match.end(1):]

        conn.execute(
            "UPDATE questions SET prompt = ?, prompt_sanskrit = ?, explanation = ?, "
            "options_json = ?, correct_answer_json = ? WHERE id = ?",
            (prompt, prompt_sanskrit, explanation,
             json.dumps(options, ensure_ascii=False), json.dumps(answer, ensure_ascii=False), question["id"]),
        )
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM vocabulary").fetchone()[0]
    devanagari_count = conn.execute(
        "SELECT COUNT(*) FROM vocabulary WHERE word_sanskrit GLOB '*[\u0900-\u097f]*'"
    ).fetchone()[0]
    transliteration_count = conn.execute(
        "SELECT COUNT(*) FROM vocabulary WHERE word_transliteration IS NOT NULL AND TRIM(word_transliteration) != ''"
    ).fetchone()[0]
    conn.close()
    print(json.dumps({
        "vocabulary_rows": total,
        "sanskrit_devanagari_rows": devanagari_count,
        "rows_with_transliteration": transliteration_count,
        "invalid_non_sanskrit_rows_removed": len(invalid_ids),
        "vocabulary_questions_updated": len(questions),
    }, indent=2))


if __name__ == "__main__":
    main()
