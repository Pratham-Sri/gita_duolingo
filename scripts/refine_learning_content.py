"""Backfill broad Sanskrit word classes and improve existing quiz choices."""

import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gitalingo.generator import (  # noqa: E402
    generate_metaphor_question,
    generate_philosophical_question,
    generate_scenario_question,
    generate_takeaway_question,
    get_db_connection,
    init_db,
)
from gitalingo.learning_content import (  # noqa: E402
    build_fill_blank_options,
    build_vocab_options,
    grammatical_info,
    translation_distractors,
)


def update_question(conn, question_id, question_type, options, answer):
    conn.execute(
        "UPDATE questions SET question_type = ?, options_json = ?, correct_answer_json = ? WHERE id = ?",
        (question_type, json.dumps(options, ensure_ascii=False), json.dumps(answer, ensure_ascii=False), question_id),
    )


def main():
    init_db()
    conn = get_db_connection()
    verses = [dict(row) for row in conn.execute(
        "SELECT verse_key, chapter_number, verse_number, text_devanagari, transliteration, translation_en, speaker FROM verses"
    )]
    verse_by_key = {row["verse_key"]: row for row in verses}
    corpus_texts = [row["text_devanagari"] for row in verses]
    vocab = [dict(row) for row in conn.execute(
        "SELECT id, verse_key, word_sanskrit, word_transliteration, meaning_en FROM vocabulary"
    )]
    for word in vocab:
        word["grammatical_info"] = grammatical_info(word["word_sanskrit"], word["meaning_en"])
        conn.execute(
            "UPDATE vocabulary SET grammatical_info = ? WHERE id = ?",
            (word["grammatical_info"], word["id"]),
        )
    meanings = [{"value": row["meaning_en"], "grammatical_info": row["grammatical_info"]}
                for row in vocab]
    words = [{"value": row["word_sanskrit"], "grammatical_info": row["grammatical_info"]}
             for row in vocab]
    by_verse = {}
    for word in vocab:
        by_verse.setdefault(word["verse_key"], []).append(word)
    chapter_meta = {
        row["chapter_number"]: dict(row)
        for row in conn.execute("SELECT * FROM chapters")
    }

    changed = {"grammar": len(vocab), "fill_blank": 0, "vocabulary_mcq": 0,
               "translation_mcq": 0, "interpretation": 0, "scenario": 0, "takeaway": 0}
    questions = [dict(row) for row in conn.execute(
        "SELECT * FROM questions ORDER BY chapter_number, verse_number, question_order"
    )]
    for question in questions:
        key = question["verse_key"]
        verse = verse_by_key[key]
        answer = json.loads(question["correct_answer_json"])
        q_type = question["question_type"]
        order = question["question_order"]
        options = None

        if q_type == "fill_blank":
            options = build_fill_blank_options(
                answer, question.get("prompt_sanskrit") or question["prompt"],
                corpus_texts, f"{key}:{order}",
            )
            changed["fill_blank"] += 1
        elif q_type == "mcq_vocab":
            target_token = question.get("prompt_sanskrit") or ""
            target = next((item for item in by_verse.get(key, [])
                           if target_token in {item["word_sanskrit"], item["word_transliteration"]}), None)
            if target:
                options = build_vocab_options(
                    answer, meanings, target["grammatical_info"],
                    excluded=[item["meaning_en"] for item in by_verse.get(key, [])],
                    seed=f"{key}:{order}",
                    fallbacks=("the field of action", "the highest self", "steadfast wisdom"),
                )
                changed["vocabulary_mcq"] += 1
        elif q_type == "mcq_reverse_vocab":
            match = re.search(r'means:\s*"(.+?)"', question["prompt"])
            target_meaning = match.group(1) if match else ""
            target = next((item for item in by_verse.get(key, [])
                           if item["meaning_en"] == target_meaning), None)
            if target:
                answer = target["word_sanskrit"]
                options = build_vocab_options(
                    answer, words, target["grammatical_info"],
                    excluded=[item["word_sanskrit"] for item in by_verse.get(key, [])],
                    seed=f"{key}:{order}",
                    fallbacks=("धर्मक्षेत्रे", "कर्मयोगेन", "आत्मतत्त्ववित्"),
                )
                changed["vocabulary_mcq"] += 1
        elif q_type == "translation_mcq":
            candidates = [row for row in verses
                          if row["chapter_number"] == verse["chapter_number"]
                          and row["verse_key"] != key]
            options = translation_distractors(
                answer, verse["verse_number"], candidates, seed=f"{key}:{order}",
            )
            changed["translation_mcq"] += 1
        elif q_type == "philosophical_insight" and order == 11:
            generated = generate_philosophical_question(
                verse["chapter_number"], verse["verse_number"], verse["text_devanagari"],
                verse["translation_en"], verse["speaker"],
            )
            generated_options = json.loads(generated["options_json"])
            if answer in generated_options:
                options = generated_options
                changed["interpretation"] += 1
        elif q_type == "philosophical_insight" and order == 13:
            generated = generate_metaphor_question(
                verse["chapter_number"], verse["verse_number"], verse["text_devanagari"],
                verse["translation_en"],
            )
            generated_options = json.loads(generated["options_json"])
            if answer in generated_options:
                options = generated_options
                changed["interpretation"] += 1
        elif q_type == "life_scenario":
            generated = generate_scenario_question(
                verse["chapter_number"], verse["verse_number"], verse["translation_en"],
                chapter_meta[verse["chapter_number"]],
            )
            generated_options = json.loads(generated["options_json"])
            if answer in generated_options:
                options = generated_options
                changed["scenario"] += 1
        elif q_type in {"true_false", "takeaway"} and order == 14:
            generated = generate_takeaway_question(
                verse["chapter_number"], verse["verse_number"], verse["translation_en"],
            )
            generated_options = json.loads(generated["options_json"])
            answer = json.loads(generated["correct_answer_json"])
            if answer in generated_options:
                options = generated_options
                q_type = generated["question_type"]
                conn.execute(
                    "UPDATE questions SET correct_answer_json = ? WHERE id = ?",
                    (json.dumps(answer, ensure_ascii=False), question["id"]),
                )
                changed["takeaway"] += 1

        if options:
            # Keep four distinct choices for selection questions. True/false
            # context items and matching/order activities retain their shapes.
            if q_type not in {"true_false", "match_pairs", "word_order"}:
                options = list(dict.fromkeys(options))[:4]
                while len(options) < 4:
                    options.append(f"A different interpretation of verse {key} ({len(options) + 1})")
                if answer not in options:
                    options[-1] = answer
            options.sort(key=str.casefold)
            random.Random(f"{key}:{order}").shuffle(options)
            update_question(conn, question["id"], q_type, options, answer)

    conn.commit()
    conn.close()
    print(json.dumps(changed, indent=2))


if __name__ == "__main__":
    main()
