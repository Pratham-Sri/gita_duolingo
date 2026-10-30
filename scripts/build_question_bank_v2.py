"""Build the complete, review-gated core bank from verse-aligned QA candidates.

The Hugging Face Q&A rows are candidate material only. Output status is always
editorial-review-required, and this script never replaces the active app bank.
"""

import csv
import json
import random
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / "data" / "core_verse_selection.json"
QA_CSV = ROOT / "cache" / "hf_english_qa.csv"
DB = ROOT / "database" / "gita_duolingo.db"
JSON_OUT = ROOT / "data" / "curated_question_bank.json"
CSV_OUT = ROOT / "exports" / "curated_question_bank_review.csv"
EXTENSION_COLUMNS = [
    ("question_key", "TEXT"), ("skill", "TEXT"), ("concept", "TEXT"),
    ("prerequisite_concept", "TEXT"), ("prerequisite_verse", "TEXT"),
    ("source", "TEXT"), ("source_question", "TEXT"), ("correct_position", "TEXT"),
    ("sanskrit", "TEXT"), ("transliteration", "TEXT"), ("base_translation", "TEXT"),
    ("status", "TEXT NOT NULL DEFAULT 'legacy'"), ("editor_notes", "TEXT"),
    ("difficulty_status", "TEXT NOT NULL DEFAULT 'legacy'"),
]


def align_legacy_schema(conn):
    """Add nullable v2 metadata to the legacy table without changing its app columns."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(questions)")}
    for name, definition in EXTENSION_COLUMNS:
        if name not in existing:
            conn.execute(f"ALTER TABLE questions ADD COLUMN {name} {definition}")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_questions_question_key ON questions(question_key)")
    conn.execute("UPDATE questions SET question_key = 'legacy:' || id WHERE question_key IS NULL")
    conn.execute("UPDATE questions SET status = 'legacy', difficulty_status = 'legacy' WHERE status IS NULL OR difficulty_status IS NULL")


def common_table_ddl(table_name):
    """Canonical interchange schema shared by legacy and current bank tables."""
    return f"""CREATE TABLE {table_name} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        verse_id INTEGER NOT NULL,
        verse_key TEXT NOT NULL,
        chapter_number INTEGER NOT NULL,
        verse_number INTEGER NOT NULL,
        lesson_level INTEGER NOT NULL DEFAULT 1,
        question_order INTEGER NOT NULL,
        question_type TEXT NOT NULL,
        difficulty TEXT NOT NULL CHECK(difficulty IN ('beginner','intermediate','advanced')),
        instruction TEXT NOT NULL,
        prompt TEXT NOT NULL,
        prompt_sanskrit TEXT,
        options_json TEXT NOT NULL,
        correct_answer_json TEXT NOT NULL,
        explanation TEXT NOT NULL,
        hint TEXT,
        xp_points INTEGER NOT NULL DEFAULT 10,
        question_key TEXT UNIQUE,
        skill TEXT,
        concept TEXT,
        prerequisite_concept TEXT,
        prerequisite_verse TEXT,
        source TEXT,
        source_question TEXT,
        correct_position TEXT,
        sanskrit TEXT,
        transliteration TEXT,
        base_translation TEXT,
        status TEXT NOT NULL DEFAULT 'legacy',
        editor_notes TEXT,
        difficulty_status TEXT NOT NULL DEFAULT 'legacy',
        FOREIGN KEY(verse_id) REFERENCES verses(id)
    )"""

TYPE_ORDER = ["meaning", "context", "inference", "application", "vocabulary"]
SKILLS = {"meaning": "interpretation", "context": "recall", "inference": "inference",
          "application": "transfer", "vocabulary": "interpretation"}
PATTERNS = {
    "meaning": re.compile(r"what does|what is the meaning|what does .* say|what is .* instruction|what is .* teaching", re.I),
    "context": re.compile(r"who |to whom|why does|why is|what prompted|what concern|in what context", re.I),
    "inference": re.compile(r"significance|imply|suggest|reveal|lesson|what follows|broader", re.I),
    "application": re.compile(r"how can|how does .* apply|everyday|daily life|practice .* life|apply .* life", re.I),
}


def normalize_display(text):
    text = re.sub(r"\s*\|\|\s*[०-९0-9]+\s*[-–]\s*[०-९0-9]+\s*\|\|", "", text or "")
    text = re.sub(r"\s*॥\s*[०-९0-9]+\s*[-–]\s*[०-९0-9]+\s*॥", "", text)
    text = re.sub(r"\s*॥\s*[०-९0-9]+\s*॥", "", text)
    text = re.sub(r"\s*\|\s*", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def short_answer(text, limit=35):
    text = re.sub(r"\s+", " ", text or "").strip()
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chosen = sentences[0] if sentences else text
    if len(chosen.split()) > limit:
        # Prefer a complete, shorter sentence from the answer rather than a cut fragment.
        candidates = [s for s in sentences if 5 <= len(s.split()) <= limit]
        if candidates:
            chosen = candidates[0]
    return chosen.strip(" \n\r\t")


def sentence_units(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text or ""))
            if 5 <= len(s.split()) <= 35]


def sanskrit_stem(text):
    return "".join(ch for ch in unicodedata.normalize("NFD", text or "")
                   if unicodedata.category(ch) != "Mn")


def candidate_score(question, kind):
    q = question.casefold()
    return sum(bool(re.search(pattern, q)) for pattern in [PATTERNS[kind]])


def choose_qa(rows):
    chosen = {}
    used = set()
    for kind in TYPE_ORDER[:-1]:
        choices = [(candidate_score(row["question"], kind), -len(row["question"]), i, row)
                   for i, row in enumerate(rows) if i not in used]
        choices.sort(reverse=True, key=lambda x: (x[0], x[1]))
        if choices and choices[0][0] > 0:
            _, _, index, row = choices[0]
            chosen[kind] = row
            used.add(index)
    # Fill gaps with unused, nonduplicate candidates, retaining five rows per verse.
    for kind in TYPE_ORDER[:-1]:
        if kind not in chosen:
            row = next((r for i, r in enumerate(rows) if i not in used), rows[0])
            chosen[kind] = row
            used.add(rows.index(row))
    return chosen


def concept_prerequisite(concept):
    prerequisites = {
        "self_and_body": ("", ""), "duty": ("self_and_body", "BG2.13"),
        "karma_yoga": ("duty", "BG2.31"), "steady_wisdom": ("karma_yoga", "BG2.47"),
        "divine_descent": ("karma_yoga", "BG2.47"),
        "knowledge_and_action": ("karma_yoga", "BG2.47"), "renunciation_and_action": ("karma_yoga", "BG2.47"),
        "meditation": ("self_and_body", "BG2.13"), "knowledge_and_devotion": ("karma_yoga", "BG2.47"),
        "remembrance_at_death": ("self_and_body", "BG2.13"), "devotion_and_grace": ("knowledge_and_devotion", "BG7.7"),
        "divine_manifestations": ("knowledge_and_devotion", "BG7.7"), "universal_form": ("divine_manifestations", "BG10.8"),
        "devotional_qualities": ("knowledge_and_devotion", "BG7.7"), "field_and_knower": ("self_and_body", "BG2.13"),
        "three_gunas": ("field_and_knower", "BG13.2"), "supreme_person": ("self_and_body", "BG2.13"),
        "ethical_qualities": ("three_gunas", "BG14.5"), "faith_and_practice": ("ethical_qualities", "BG16.1"),
        "choice_and_surrender": ("karma_yoga", "BG2.47"),
    }
    return prerequisites.get(concept, ("", ""))


def difficulty_for(kind, prompt, answer):
    """Content-based provisional estimate; learner telemetry should replace it."""
    words = (prompt + " " + answer).split()
    dense_terms = len(re.findall(r"\b(?:dharma|karma|yoga|ātman|brahman|prakṛti|guṇa|surrender|renunciation|equanimity)\b", (prompt + " " + answer).casefold()))
    if kind == "vocabulary":
        return "beginner" if len(answer.split()) <= 2 else "intermediate"
    if len(words) > 43 or dense_terms >= 3 or kind == "application":
        return "advanced"
    if len(words) > 26 or dense_terms >= 1 or kind == "inference":
        return "intermediate"
    return "beginner"


OVERRIDES = {
    ("BG18.66", "context"): {
        "prompt": "How does BG18.63 shape the way to read Krishna’s assurance in BG18.66?",
        "answer": "BG18.63 asks Arjuna to reflect fully and then choose; BG18.66 follows with Krishna’s assurance of refuge and release.",
        "options": [
            "BG18.63 asks Arjuna to reflect fully and then choose; BG18.66 follows with Krishna’s assurance of refuge and release.",
            "BG18.63 makes Arjuna’s choice irrelevant, and BG18.66 removes the need to reflect on the teaching.",
            "BG18.63 asks Arjuna to abandon the teaching, while BG18.66 begins a separate topic about warfare.",
            "BG18.66 gives its assurance first, and BG18.63 later asks Arjuna to consider whether to accept it.",
        ],
        "explanation": "BG18.63 comes before BG18.66: Krishna asks Arjuna to reflect on the teaching and then act as he chooses. The assurance of refuge in 18.66 follows that appeal.",
    },
    ("BG18.66", "application"): {
        "prompt": "A reader says BG18.66 cancels the reflection and choice Krishna gave Arjuna in BG18.63. Which response best follows the sequence?",
        "answer": "BG18.63 first asks Arjuna to reflect and choose; BG18.66 then gives an assurance of refuge, so the later appeal should be read in that sequence.",
        "options": [
            "BG18.63 first asks Arjuna to reflect and choose; BG18.66 then gives an assurance of refuge, so the later appeal should be read in that sequence.",
            "BG18.66 comes before BG18.63, so the assurance removes the need for Arjuna to hear the teaching or make a choice.",
            "BG18.63 asks Arjuna to reject Krishna’s teaching, and BG18.66 changes the subject to a different kind of refuge.",
            "BG18.63 and BG18.66 contradict each other, so a reader must discard one of the two verses.",
        ],
        "explanation": "The order is 18.63 followed by 18.66. The first verse explicitly invites reflection and choice; the later verse gives a final assurance. Reading their sequence avoids claiming that 18.66 erases 18.63.",
    },
    ("BG4.7", "application"): {
        "prompt": "A friend says BG4.7 guarantees an immediate divine rescue whenever injustice appears. Which reading stays closest to the verse?",
        "answer": "The verse says Krishna manifests when dharma declines and adharma rises; it does not specify an immediate timetable for every crisis.",
        "options": [
            "The verse says Krishna manifests when dharma declines and adharma rises; it does not specify an immediate timetable for every crisis.",
            "The verse instructs people to wait passively for a miracle whenever injustice appears in their community.",
            "The verse makes any political leader who claims a moral cause an incarnation of Krishna.",
            "The verse guarantees social order will quickly return whenever a community sees wrongdoing.",
        ],
        "explanation": "BG4.7 describes Krishna’s manifestation when dharma declines and adharma rises. It is not a direct instruction to human bystanders and does not set a timetable for events.",
    },
}


def choose_vocab(words, verse_text, verse_key):
    valid = []
    for row in words:
        sa = row["word_sanskrit"] or ""
        gloss = (row["meaning_en"] or "").strip()
        if re.search(r"[A-Za-z]", sa) or not gloss or len(gloss.split()) > 8:
            continue
        if sanskrit_stem(sa) not in sanskrit_stem(verse_text):
            continue
        if gloss.casefold() in {"and", "but", "the", "i", "you", "me"}:
            continue
        valid.append(row)
    if not valid:
        fallbacks = {
            "BG8.5": {"word_sanskrit": "स्मरन्", "word_transliteration": "smaran", "meaning_en": "remembering"},
            "BG12.18": {"word_sanskrit": "समः", "word_transliteration": "samaḥ", "meaning_en": "equal-minded"},
        }
        return fallbacks.get(verse_key)
    # Favor a meaningful, relatively short term instead of an inflected particle.
    return max(valid, key=lambda r: (len(r["word_sanskrit"]), -len(r["meaning_en"].split())))


def make_options(answer, distractor_candidates, seed):
    unique = []
    for candidate in distractor_candidates:
        candidate = short_answer(candidate)
        if candidate and candidate.casefold() != answer.casefold() and candidate not in unique:
            unique.append(candidate)
    unique.sort(key=lambda x: abs(len(x) - len(answer)))
    selected = unique[:3]
    if len(selected) < 3:
        # Never pad with generic options; fail so the item is sent for authoring.
        raise RuntimeError(f"Cannot find three length-balanced distractors for {seed}")
    options = [answer, *selected]
    random.Random(seed).shuffle(options)
    return options


def main():
    selection = json.loads(SELECTION.read_text(encoding="utf-8"))
    selected = selection["core_verse_keys"]
    qa_by_key = defaultdict(list)
    with QA_CSV.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            key = f"BG{row['chapter_no']}.{row['verse_no']}"
            qa_by_key[key].append(row)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    align_legacy_schema(conn)
    conn.commit()
    verses = {r["verse_key"]: dict(r) for r in conn.execute("SELECT * FROM verses")}
    words_by_key = defaultdict(list)
    for row in conn.execute("SELECT verse_key, word_sanskrit, word_transliteration, meaning_en, grammatical_info FROM vocabulary"):
        words_by_key[row["verse_key"]].append(dict(row))
    all_words = [w for group in words_by_key.values() for w in group]
    payload = {"schema_version": "curated-question-bank-v2", "status": "editorial-review-required",
               "source_policy": "Q&A data is idea material only; every answer needs human verification against Sanskrit and the cited Purohit Swami translation.",
               "questions": []}
    for key in selected:
        verse = verses[key]
        qa_rows = qa_by_key.get(key, [])
        if len(qa_rows) < 4:
            raise RuntimeError(f"QA candidates missing for {key}")
        chosen = choose_qa(qa_rows)
        all_answers = [short_answer(row["answer"]) for row in qa_rows]
        concept = selection["concept_by_verse"][key]
        prereq_concept, prereq = concept_prerequisite(concept)
        verse_text = normalize_display(verse["text_devanagari"])
        transliteration = normalize_display(verse["transliteration"]).replace("mokṣyayiṣyāmi", "mokṣayiṣyāmi")
        for order, kind in enumerate(TYPE_ORDER, start=1):
            source = "JDhruv14/Bhagavad-Gita-QA candidate; verify before use"
            if kind == "vocabulary":
                vocab = choose_vocab(words_by_key[key], verse_text, key)
                if vocab:
                    answer = vocab["meaning_en"].strip()
                    prompt = f"In this verse, what does {vocab['word_sanskrit']} ({vocab['word_transliteration']}) mean?"
                    distractors = [w["meaning_en"] for w in words_by_key[key]
                                   if w is not vocab and not re.search(r"[A-Za-z]", w["word_sanskrit"])
                                   and w["word_sanskrit"] in verse_text and len(w["meaning_en"].split()) <= 8]
                    distractors.extend(w["meaning_en"] for w in all_words
                                       if w["verse_key"] != key
                                       and not re.search(r"[A-Za-z]", w["word_sanskrit"])
                                       and w["meaning_en"] and len(w["meaning_en"].split()) <= 8)
                    options = make_options(answer, distractors, f"{key}:{kind}")
                    explanation = f"In the verse, {vocab['word_sanskrit']} ({vocab['word_transliteration']}) is glossed as ‘{answer}’. Verify this lexical sense in context."
                    source = "Local verse-word gloss; verify against the verse"
                else:
                    raise RuntimeError(f"No clean verse-word gloss for {key}")
            else:
                row = chosen[kind]
                answer = short_answer(row["answer"])
                prompt = row["question"].strip()
                override = OVERRIDES.get((key, kind))
                if override:
                    prompt, answer = override["prompt"], override["answer"]
                distractors = [sentence for row_answer in (r["answer"] for r in qa_rows)
                               for sentence in sentence_units(row_answer)
                               if sentence.casefold() != answer.casefold()]
                options = override["options"] if override else make_options(answer, distractors, f"{key}:{kind}")
                explanation = override["explanation"] if override else (row["answer"].strip() + " [Candidate explanation; check claims and attribution before publication]")
            # Use source order as a stable tie-breaker but shuffle answer position.
            payload["questions"].append({
                "id": f"{key}.{kind}.{order:02d}", "verse_key": key,
                "question_type": kind, "skill": SKILLS[kind],
                "difficulty": difficulty_for(kind, prompt, answer), "difficulty_status": "provisional",
                "concept": concept, "prerequisite_concept": prereq_concept,
                "prerequisite_verse": prereq,
                "source": source, "prompt": prompt, "options": options,
                "correct_answer": answer, "explanation": explanation,
                "sanskrit": verse_text, "transliteration": transliteration,
                "base_translation": "Purohit Swami (1935), reference only; not the learner-facing paraphrase",
                "source_question": "Editor-authored" if (key, kind) in OVERRIDES else row["question"] if kind != "vocabulary" else "Lexical gloss from local verse-word collection",
                "status": "editorial-review-required",
                "editor_notes": "Verify meaning against Sanskrit; review distractor plausibility, doctrinal scope, and source rights.",
            })
    conn.close()
    # Balance correct-answer positions across the full export without changing options.
    positions = [i % 4 for i in range(len(payload["questions"]))]
    random.Random("gitalingo-v2-position-balance").shuffle(positions)
    for q, pos in zip(payload["questions"], positions):
        answer = q["correct_answer"]
        rest = [o for o in q["options"] if o != answer]
        rng = random.Random(q["id"] + ":display")
        rng.shuffle(rest)
        q["options"] = rest[:pos] + [answer] + rest[pos:]
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    fields = ["status", "id", "verse_key", "question_type", "skill", "difficulty", "difficulty_status",
              "concept", "prerequisite_concept", "prerequisite_verse", "prompt", "option_a", "option_b", "option_c", "option_d",
              "correct_answer", "correct_position", "explanation", "sanskrit", "transliteration",
              "base_translation", "source", "source_question", "editor_notes"]
    with CSV_OUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for q in payload["questions"]:
            writer.writerow({**{k: q.get(k, "") for k in fields if k not in {"option_a", "option_b", "option_c", "option_d", "correct_position"}},
                             **{f"option_{chr(97+i)}": o for i, o in enumerate(q["options"])},
                             "correct_position": "ABCD"[q["options"].index(q["correct_answer"])]})
    # The legacy and current banks share one additive, app-compatible schema.
    # Core verses use reviewed-bank candidates; other verses retain legacy items
    # with an explicit status so a full-corpus lesson path never runs out.
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("DROP TABLE IF EXISTS curated_questions_v2")
    conn.execute(common_table_ddl("curated_questions_v2"))
    curated_rows = []
    verse_meta = {r["verse_key"]: r for r in conn.execute("SELECT id, verse_key, chapter_number, verse_number FROM verses")}
    level_by_type = {"vocabulary": 1, "meaning": 3, "context": 3, "inference": 4, "application": 4}
    instruction_by_type = {"vocabulary": "Choose the word meaning", "meaning": "Choose the best meaning",
                           "context": "Choose the dialogue context", "inference": "Choose the best inference",
                           "application": "Apply the teaching"}
    for q in payload["questions"]:
        verse = verse_meta[q["verse_key"]]
        position = "ABCD"[q["options"].index(q["correct_answer"])]
        curated_rows.append((
            verse["id"], q["verse_key"], verse["chapter_number"], verse["verse_number"],
            level_by_type[q["question_type"]], int(q["id"].rsplit(".", 1)[1]), q["question_type"],
            q["difficulty"], instruction_by_type[q["question_type"]], q["prompt"], q["sanskrit"],
            json.dumps(q["options"], ensure_ascii=False), json.dumps(q["correct_answer"], ensure_ascii=False),
            q["explanation"], None, 10, q["id"], q["skill"], q["concept"], q["prerequisite_concept"],
            q["prerequisite_verse"], q["source"], q["source_question"], position, q["sanskrit"],
            q["transliteration"], q["base_translation"], q["status"], q["editor_notes"], q["difficulty_status"],
        ))
    insert_sql = """INSERT INTO curated_questions_v2 (
        verse_id,verse_key,chapter_number,verse_number,lesson_level,question_order,question_type,
        difficulty,instruction,prompt,prompt_sanskrit,options_json,correct_answer_json,explanation,
        hint,xp_points,question_key,skill,concept,prerequisite_concept,prerequisite_verse,source,
        source_question,correct_position,sanskrit,transliteration,base_translation,status,editor_notes,difficulty_status
    ) VALUES """ + "(" + ",".join("?" for _ in range(30)) + ")"
    conn.executemany(insert_sql, curated_rows)
    selected_placeholders = ",".join("?" for _ in selected)
    conn.execute(f"""INSERT INTO curated_questions_v2 (
        verse_id,verse_key,chapter_number,verse_number,lesson_level,question_order,question_type,
        difficulty,instruction,prompt,prompt_sanskrit,options_json,correct_answer_json,explanation,
        hint,xp_points,question_key,skill,concept,prerequisite_concept,prerequisite_verse,source,
        source_question,correct_position,sanskrit,transliteration,base_translation,status,editor_notes,difficulty_status
    ) SELECT q.verse_id,q.verse_key,q.chapter_number,q.verse_number,q.lesson_level,q.question_order,
        q.question_type,q.difficulty,q.instruction,q.prompt,q.prompt_sanskrit,q.options_json,
        q.correct_answer_json,q.explanation,q.hint,q.xp_points,'legacy:'||q.id,NULL,NULL,NULL,NULL,
        'Legacy question bank; retained for verse coverage','legacy:'||q.id,NULL,v.text_devanagari,
        v.transliteration,v.translation_source,'legacy-fallback','Legacy question retained until this verse is curated.', 'legacy'
    FROM questions q JOIN verses v ON v.id=q.verse_id
    WHERE q.verse_key NOT IN ({selected_placeholders})""", selected)
    conn.execute("CREATE INDEX idx_curated_questions_v2_verse ON curated_questions_v2(verse_key)")
    conn.execute("CREATE INDEX idx_curated_questions_v2_type ON curated_questions_v2(question_type)")
    conn.execute("CREATE INDEX idx_curated_questions_v2_level ON curated_questions_v2(lesson_level)")
    # Same columns and order are required for drop-in table selection.
    legacy_columns = [row[1] for row in conn.execute("PRAGMA table_info(questions)")]
    current_columns = [row[1] for row in conn.execute("PRAGMA table_info(curated_questions_v2)")]
    if legacy_columns != current_columns:
        raise RuntimeError(f"Question-bank schemas differ: legacy={legacy_columns}, current={current_columns}")
    coverage = conn.execute("SELECT COUNT(*),COUNT(DISTINCT verse_key) FROM curated_questions_v2").fetchone()
    fallback_rows = conn.execute("SELECT COUNT(*) FROM curated_questions_v2 WHERE status='legacy-fallback'").fetchone()[0]
    total_source_verses = conn.execute("SELECT COUNT(*) FROM verses").fetchone()[0]
    if coverage[1] != total_source_verses:
        raise RuntimeError(f"Current bank covers {coverage[1]} of {total_source_verses} source verses")
    conn.commit()
    conn.close()
    print(json.dumps({"curated_verses": len(selected), "curated_questions": len(payload["questions"]),
                      "current_bank_questions_in_sqlite": coverage[0],
                      "source_verses_with_questions": coverage[1], "legacy_fallback_questions": fallback_rows,
                      "schemas_identical": True,
                      "types": dict(Counter(q["question_type"] for q in payload["questions"])),
                      "answer_positions": dict(Counter(q["options"].index(q["correct_answer"]) for q in payload["questions"])),
                      "json": str(JSON_OUT), "csv": str(CSV_OUT)}, indent=2))


if __name__ == "__main__":
    main()
