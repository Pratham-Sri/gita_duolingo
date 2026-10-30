"""Report structural and editorial risks in the generated question bank."""

import json
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "database" / "gita_duolingo.db"
OUT = ROOT / "exports" / "question_bank_audit.json"
ARTIFACTS = re.compile(r"(?:ï\d|�|Ã.|Â.|â€|\ufffd)")


def clean(text):
    text = unicodedata.normalize("NFKC", text or "").casefold()
    return re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)


def wordset(text):
    return set(clean(text).split())


def main():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    verses = {r["verse_key"]: dict(r) for r in conn.execute(
        "SELECT verse_key, chapter_number, verse_number, translation_en FROM verses"
    )}
    rows = [dict(r) for r in conn.execute("SELECT * FROM questions ORDER BY verse_key, question_order")]
    conn.close()
    findings = Counter()
    per_verse = defaultdict(list)
    answer_positions = Counter()
    bad_examples = defaultdict(list)
    stem_counts = Counter()
    for q in rows:
        key = q["verse_key"]
        per_verse[key].append(q)
        stem_counts[q["prompt"]] += 1
        try:
            options = json.loads(q["options_json"])
            answer = json.loads(q["correct_answer_json"])
        except Exception:
            findings["malformed_json"] += 1
            continue
        if not isinstance(options, list) or not isinstance(answer, str):
            continue
        norm_options = [clean(str(o)).strip() for o in options]
        if len(norm_options) != len(set(norm_options)):
            findings["duplicate_options"] += 1
            bad_examples["duplicate_options"].append(key)
        if "\n" in q["prompt"] or "\n" in q["explanation"] or any("\n" in str(o) for o in options):
            findings["embedded_newlines"] += 1
            bad_examples["embedded_newlines"].append(key)
        if ARTIFACTS.search(" ".join([q["prompt"], q["explanation"], answer, *map(str, options)])):
            findings["encoding_artifacts"] += 1
            bad_examples["encoding_artifacts"].append(key)
        translation = verses.get(key, {}).get("translation_en", "")
        answer_norm = clean(answer).strip()
        translation_norm = clean(translation).strip()
        if len(answer_norm) >= 8 and answer_norm in translation_norm:
            findings["answer_is_translation_fragment"] += 1
            bad_examples["answer_is_translation_fragment"].append(key)
        answer_words = len(answer.split())
        if answer_words < 3:
            findings["answer_under_3_words"] += 1
            bad_examples["answer_under_3_words"].append(key)
        if answer.rstrip().endswith(("?", ",", "and", "or", "but", "of", "to", "with")):
            findings["answer_dangling_ending"] += 1
            bad_examples["answer_dangling_ending"].append(key)
        answer_set = wordset(answer)
        for i, option in enumerate(options):
            if clean(str(option)).strip() == answer_norm:
                answer_positions[i] += 1
            if i < len(options) - 1:
                a, b = wordset(str(option)), wordset(str(options[i + 1]))
                if a and b and len(a & b) / len(a | b) > 0.6:
                    findings["near_duplicate_option_pairs"] += 1
            opt_set = wordset(str(option))
            if answer_set and opt_set and len(answer_set & opt_set) / len(answer_set | opt_set) > 0.75:
                findings["answer_option_high_overlap"] += 1
        lengths = [len(str(o).split()) for o in options]
        if lengths and answer_words and abs(answer_words - sum(lengths) / len(lengths)) / max(1, sum(lengths) / len(lengths)) > 0.2:
            findings["answer_length_outside_20pct"] += 1
    gaps = []
    per_verse_counts = Counter()
    for key, qs in per_verse.items():
        per_verse_counts[len(qs)] += 1
        orders = sorted(q["question_order"] for q in qs)
        if orders and orders != list(range(orders[0], orders[-1] + 1)):
            gaps.append(key)
        if len({q["prompt"].casefold() for q in qs}) != len(qs):
            findings["duplicate_stems_within_verse"] += 1
    for stem, count in stem_counts.items():
        if count > 1:
            findings["reused_stems"] += count - 1
    report = {
        "questions": len(rows), "verses_with_questions": len(per_verse),
        "per_verse_question_count_distribution": dict(sorted(per_verse_counts.items())),
        "distinct_stems": len(stem_counts), "answer_position_counts": dict(sorted(answer_positions.items())),
        "question_order_gap_verses": len(gaps), "issues": dict(findings),
        "examples": {k: list(dict.fromkeys(v))[:12] for k, v in bad_examples.items()},
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
