"""Fail-fast validator for the curated v2 JSON question-bank contract."""

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ARTIFACTS = re.compile(r"(?:ï\d|�|Ã.|Â.|â€|\ufffd)")
REQUIRED = {
    "id", "verse_key", "question_type", "skill", "difficulty", "concept",
    "prerequisite_verse", "source", "prompt", "options", "correct_answer", "explanation",
}


def normalize(text):
    text = unicodedata.normalize("NFKC", text or "").casefold()
    return re.sub(r"[^\w\s]", " ", text).strip()


def words(text):
    return set(normalize(text).split())


def validate(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    questions = data.get("questions") if isinstance(data, dict) else data
    if not isinstance(questions, list):
        raise ValueError("Expected a JSON array or an object with a 'questions' array.")
    errors = []
    ids = set()
    by_verse = defaultdict(list)
    answer_positions = Counter()
    answer_lengths = []
    distractor_lengths = []
    correct_style = Counter()
    distractor_style = Counter()
    style_patterns = {
        "absolutist": re.compile(r"\b(?:only|every|never|guarantees?|entirely|ignore)\b", re.I),
        "balancing": re.compile(r"\b(?:while|without|not simply|even though)\b", re.I),
    }
    for index, q in enumerate(questions):
        label = q.get("id", f"row-{index + 1}")
        missing = REQUIRED - q.keys()
        if missing:
            errors.append(f"{label}: missing {', '.join(sorted(missing))}")
            continue
        if q["id"] in ids:
            errors.append(f"{label}: duplicate id")
        ids.add(q["id"])
        by_verse[q["verse_key"]].append(q)
        if q["question_type"] not in {"meaning", "context", "inference", "application", "vocabulary"}:
            errors.append(f"{label}: invalid question_type")
        if q.get("difficulty_status") != "provisional":
            errors.append(f"{label}: difficulty must be explicitly marked provisional")
        if q["skill"] not in {"recall", "interpretation", "inference", "transfer"}:
            errors.append(f"{label}: invalid skill")
        options = q["options"]
        answer = q["correct_answer"]
        if not isinstance(options, list) or len(options) != 4 or not all(isinstance(o, str) for o in options):
            errors.append(f"{label}: expected exactly four text options")
            continue
        norm_options = [normalize(o) for o in options]
        if len(set(norm_options)) != 4:
            errors.append(f"{label}: duplicate options")
        if sum(normalize(o) == normalize(answer) for o in options) != 1:
            errors.append(f"{label}: correct answer must occur exactly once in options")
        else:
            answer_positions["ABCD"[norm_options.index(normalize(answer))]] += 1
        if len(normalize(q["prompt"])) < 12:
            errors.append(f"{label}: prompt is too short")
        if not q["source"].strip() or not q["concept"].strip() or not q["explanation"].strip():
            errors.append(f"{label}: source, concept, and explanation are required")
        if q["explanation"].strip().casefold() in {"correct", "this is correct", "the answer is correct"}:
            errors.append(f"{label}: template explanation")
        text_blob = " ".join([q["prompt"], q["explanation"], answer, *options])
        if "\n" in text_blob or ARTIFACTS.search(text_blob) or re.search(r" {2,}", text_blob):
            errors.append(f"{label}: newline, encoding artifact, or repeated spaces")
        answer_words = words(answer)
        for option in options:
            if normalize(option) == normalize(answer):
                continue
            opt_words = words(option)
            overlap = len(answer_words & opt_words) / max(1, len(answer_words | opt_words))
            if overlap > 0.75:
                errors.append(f"{label}: distractor is nearly the same as the answer")
        answer_lengths.append(len(answer))
        item_distractors = [o for o in options if normalize(o) != normalize(answer)]
        distractor_lengths.extend(len(o) for o in item_distractors)
        for name, pattern in style_patterns.items():
            correct_style[name] += bool(pattern.search(answer))
            distractor_style[name] += sum(bool(pattern.search(o)) for o in item_distractors)
        if q.get("prerequisite_verse") == q["verse_key"]:
            errors.append(f"{label}: a question cannot require its own verse as a prerequisite")
    for verse_key, rows in by_verse.items():
        prompts = [normalize(q["prompt"]) for q in rows]
        if len(prompts) != len(set(prompts)):
            errors.append(f"{verse_key}: duplicate stems")
        expected_types = {"meaning", "context", "inference", "application", "vocabulary"}
        found_types = [q["question_type"] for q in rows]
        if len(rows) != 5 or set(found_types) != expected_types or len(found_types) != len(set(found_types)):
            errors.append(f"{verse_key}: expected one question of each of the five types")
    if answer_lengths and distractor_lengths:
        mean_answer = sum(answer_lengths) / len(answer_lengths)
        mean_distractor = sum(distractor_lengths) / len(distractor_lengths)
        if abs(mean_answer - mean_distractor) / max(1, mean_distractor) > 0.20:
            errors.append("bank-wide average answer length differs from average distractor length by more than 20%")
        for name in style_patterns:
            answer_rate = correct_style[name] / len(answer_lengths)
            distractor_rate = distractor_style[name] / len(distractor_lengths)
            if abs(answer_rate - distractor_rate) > 0.05:
                errors.append(f"{name} wording rate differs between correct answers and distractors by more than 5 percentage points")
    if answer_positions and max(answer_positions.values()) - min(answer_positions.values()) > 1:
        errors.append("correct answer positions are not balanced")
    return {"questions": len(questions), "verses": len(by_verse), "errors": errors}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path, nargs="?", default=Path("data/curated_question_bank.json"))
    args = parser.parse_args()
    try:
        result = validate(args.path)
    except Exception as exc:
        print(f"Validation could not run: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
