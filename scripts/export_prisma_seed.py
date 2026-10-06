"""Export source data using the app's Chapter -> Module -> Lesson -> Verse model."""

import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "gita_duolingo.db"
OUT_PATH = ROOT / "exports" / "prisma_seed_content.json"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def oid(kind: str, key: str) -> str:
    """Return a stable 24-character value suitable for BSON ObjectId conversion."""
    return hashlib.sha256(f"gitalingo:{kind}:{key}".encode("utf-8")).hexdigest()[:24]


def read_rows(conn, sql):
    return [dict(row) for row in conn.execute(sql).fetchall()]


def range_keys(section, verse_by_number):
    keys = set()
    for ref in section.get("verse_ranges", []):
        start = re.fullmatch(r"BG(\d+)\.(\d+)", ref.get("start", ""))
        end = re.fullmatch(r"BG(\d+)\.(\d+)", ref.get("end", ref.get("start", "")))
        if not start or not end:
            continue
        start_ch, start_v = map(int, start.groups())
        end_ch, end_v = map(int, end.groups())
        for chapter in range(start_ch, end_ch + 1):
            lo = start_v if chapter == start_ch else 1
            hi = end_v if chapter == end_ch else max(
                (v for ch, v in verse_by_number if ch == chapter), default=0
            )
            keys.update(
                verse_by_number[(chapter, verse)]["verse_key"]
                for verse in range(lo, hi + 1)
                if (chapter, verse) in verse_by_number
            )
    return keys


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    chapters = read_rows(conn, "SELECT * FROM chapters ORDER BY chapter_number")
    verses = read_rows(conn, "SELECT * FROM verses ORDER BY chapter_number, verse_number")
    words = read_rows(conn, "SELECT * FROM vocabulary ORDER BY verse_key, id")
    questions = read_rows(
        conn,
        "SELECT * FROM questions ORDER BY chapter_number, verse_number, lesson_level, question_order",
    )
    curriculum = json.loads((ROOT / "data" / "curriculum.json").read_text(encoding="utf-8"))
    conn.close()

    scripture_id = oid("scripture", "bhagavad-gita")
    records = defaultdict(list)
    records["scriptures"].append({
        "id": scripture_id, "slug": "bhagavad-gita", "title": "Bhagavad Gita",
        "description": "The Bhagavad Gita, organized as a structured Sanskrit learning course.",
        "author": None, "tradition": "Hindu", "coverImage": None,
        "status": "PUBLISHED", "totalChapters": len(chapters),
        "createdAt": NOW, "updatedAt": NOW,
    })
    records["scriptureTranslations"].append({
        "id": oid("scripture_translation", "bhagavad-gita:en"), "scriptureId": scripture_id,
        "language": "en", "title": "Bhagavad Gita",
        "description": "A thematic and verse-by-verse learning course.",
    })

    chapter_id_by_num = {}
    chapter_module_orders = defaultdict(lambda: 1)
    for chapter in chapters:
        number = chapter["chapter_number"]
        chapter_id = oid("chapter", str(number))
        chapter_id_by_num[number] = chapter_id
        records["chapters"].append({
            "id": chapter_id, "scriptureId": scripture_id, "number": number,
            "slug": f"chapter-{number}", "title": chapter["name_transliterated"] or f"Chapter {number}",
            "description": chapter.get("summary_en"), "difficulty": "BEGINNER",
            "status": "PUBLISHED", "order": number, "versesCount": chapter.get("verses_count"),
            "createdAt": NOW, "updatedAt": NOW,
        })
        for language, title, description in (
            ("en", chapter.get("name_meaning") or f"Chapter {number}", chapter.get("summary_en")),
            ("hi", chapter.get("name_meaning") or f"अध्याय {number}", chapter.get("summary_hi")),
            ("sa", chapter.get("name_sanskrit"), None),
        ):
            if title:
                records["chapterTranslations"].append({
                    "id": oid("chapter_translation", f"{number}:{language}"),
                    "chapterId": chapter_id, "language": language,
                    "title": title, "description": description,
                })

    verse_by_number = {(v["chapter_number"], v["verse_number"]): v for v in verses}
    verse_by_key = {v["verse_key"]: v for v in verses}

    # A Verse belongs to exactly one Lesson. Thematic sections get first claim
    # on their referenced verses; overlapping ranges use the earliest section.
    # Verses not claimed by a theme go in that chapter's core lesson. If a
    # chapter is fully theme-covered but has no theme module anchored to it,
    # keep its verses in a chapter-owned core lesson instead.
    lesson_owner = {}
    section_verse_keys = {}
    for section in curriculum["sections"]:
        keys = range_keys(section, verse_by_number)
        section_verse_keys[section["id"]] = keys
        for key in sorted(keys):
            lesson_owner.setdefault(key, f"theme:{section['id']}:{verse_by_key[key]['chapter_number']}")
    theme_anchor_chapters = {
        section["chapter_numbers"][0]
        for section in curriculum["sections"] if section.get("chapter_numbers")
    }
    for chapter in chapters:
        number = chapter["chapter_number"]
        chapter_keys = [v["verse_key"] for v in verses if v["chapter_number"] == number]
        if all(key in lesson_owner for key in chapter_keys) and number not in theme_anchor_chapters:
            for key in chapter_keys:
                lesson_owner[key] = f"chapter:{number}"
        for key in chapter_keys:
            lesson_owner.setdefault(key, f"chapter:{number}")

    lesson_id_by_owner = {}
    lesson_verse_keys = defaultdict(list)
    lesson_questions = defaultdict(list)
    lesson_order_by_module = defaultdict(int)
    module_order_by_chapter = defaultdict(lambda: 1)

    def add_module(chapter_number, slug, title, description, kind):
        module_id = oid("module", slug)
        module_order_by_chapter[chapter_number] += 1
        order = module_order_by_chapter[chapter_number] - 1
        chapter_id = chapter_id_by_num[chapter_number]
        records["modules"].append({
            "id": module_id, "chapterId": chapter_id, "slug": slug,
            "title": title, "description": description, "order": order,
            "status": "PUBLISHED", "createdAt": NOW, "updatedAt": NOW,
        })
        records["moduleTranslations"].append({
            "id": oid("module_translation", f"{slug}:en"), "moduleId": module_id,
            "language": "en", "title": title, "description": description,
        })
        return module_id

    def add_lesson(module_id, owner, slug, title, description, order, objectives=None):
        lesson_id = oid("lesson", slug)
        lesson_id_by_owner[owner] = lesson_id
        records["lessons"].append({
            "id": lesson_id, "moduleId": module_id, "slug": slug,
            "title": title, "description": description, "order": order,
            "estimatedMinutes": None, "difficulty": "BEGINNER", "xpReward": 50,
            "status": "PUBLISHED", "createdAt": NOW, "updatedAt": NOW,
        })
        records["lessonTranslations"].append({
            "id": oid("lesson_translation", f"{slug}:en"), "lessonId": lesson_id,
            "language": "en", "title": title, "description": description,
        })
        records["lessonContentBlocks"].extend([
            {"id": oid("content_block", f"{slug}:intro"), "lessonId": lesson_id,
             "type": "INTRO", "order": 1, "title": title, "content": description, "metadata": None},
            {"id": oid("content_block", f"{slug}:summary"), "lessonId": lesson_id,
             "type": "KEY_TAKEAWAY", "order": 2, "title": "Learning objectives",
             "content": "\n".join(f"• {item}" for item in (objectives or [])),
             "metadata": json.dumps({"owner": owner}, ensure_ascii=False)},
        ])
        return lesson_id

    # Chapter modules and lessons own all verses not assigned to thematic lessons.
    for chapter in chapters:
        number = chapter["chapter_number"]
        owner = f"chapter:{number}"
        keys = sorted(k for k, value in lesson_owner.items() if value == owner)
        if not keys:
            continue
        title = f"Chapter {number}: Core Verses"
        desc = f"Study verses from Chapter {number} that are not assigned to a thematic section."
        module_id = add_module(number, f"chapter-{number}-core", title, desc, "chapter")
        lesson_id = add_lesson(module_id, owner, f"chapter-{number}-core-verses", title, desc, 1)
        lesson_verse_keys[lesson_id].extend(keys)

    # Thematic sections become modules. A section spanning multiple source
    # chapters gets one lesson per chapter to honor @@unique([lessonId, verseNumber]).
    thematic_first_lesson = {}
    for section in curriculum["sections"]:
        section_id = section["id"]
        anchor = (section.get("chapter_numbers") or [1])[0]
        module_id = add_module(anchor, f"theme-{section_id}", section["title"], section["description"], "theme")
        owned = [key for key in section_verse_keys[section_id]
                 if lesson_owner.get(key, "").startswith(f"theme:{section_id}:")]
        by_chapter = defaultdict(list)
        for key in owned:
            by_chapter[verse_by_key[key]["chapter_number"]].append(key)
        if not by_chapter:
            by_chapter[anchor] = []
        for lesson_order, number in enumerate(sorted(by_chapter), start=1):
            owner = f"theme:{section_id}:{number}"
            keys = sorted(by_chapter[number])
            suffix = f"-chapter-{number}" if len(by_chapter) > 1 else ""
            lesson_id = add_lesson(
                module_id, owner, f"{section_id}{suffix}",
                section["subtitle"] if not suffix else f"{section['subtitle']} — Chapter {number}",
                section["description"], lesson_order, section.get("learning_objectives"),
            )
            lesson_verse_keys[lesson_id].extend(keys)
            thematic_first_lesson.setdefault(section_id, lesson_id)
        theme_lesson_id = thematic_first_lesson.get(section_id)
        if theme_lesson_id:
            records["lessonContentBlocks"].append({
                "id": oid("thematic_content", f"{section_id}:range"),
                "lessonId": theme_lesson_id, "type": "EXPLANATION", "order": 3,
                "title": "Verse references", "content": section["description"],
                "metadata": json.dumps({
                    "sectionId": section_id, "verseRanges": section.get("verse_ranges", []),
                    "chapterNumbers": section.get("chapter_numbers", []),
                }, ensure_ascii=False),
            })

    lesson_id_by_verse = {}
    for owner, lesson_id in lesson_id_by_owner.items():
        for key in lesson_verse_keys[lesson_id]:
            lesson_id_by_verse[key] = lesson_id
    if set(lesson_id_by_verse) != set(verse_by_key):
        raise ValueError("Every source verse must belong to exactly one lesson")

    verse_id_by_key = {}
    for verse in verses:
        key = verse["verse_key"]
        verse_id = oid("verse", key)
        verse_id_by_key[key] = verse_id
        records["verses"].append({
            "id": verse_id, "lessonId": lesson_id_by_verse[key],
            "verseKey": key, "verseNumber": verse["verse_number"],
            "sanskrit": verse["text_devanagari"], "transliteration": verse["transliteration"],
            "audioUrl": None, "speaker": verse.get("speaker"),
            "commentarySummary": verse.get("commentary_summary"),
            "createdAt": NOW, "updatedAt": NOW,
        })
        for language, kind, content, source in (
            ("en", "CONTEMPORARY", verse.get("translation_en"), verse.get("translation_source")),
            ("en", "PRACTICAL", verse.get("meaning_en"), "GitaLingo contextual learning meaning"),
            ("hi", "CONTEMPORARY", verse.get("translation_hi"), None),
        ):
            if content:
                records["verseTranslations"].append({
                    "id": oid("verse_translation", f"{key}:{language}:{kind}"),
                    "verseId": verse_id, "language": language, "type": kind,
                    "content": content, "source": source, "author": None,
                    "createdAt": NOW, "updatedAt": NOW,
                })

    word_positions = defaultdict(int)
    for word in words:
        key = word["verse_key"]
        word_positions[key] += 1
        records["verseWords"].append({
            "id": oid("verse_word", f"{key}:{word['id']}"),
            "verseId": verse_id_by_key[key], "position": word_positions[key],
            "sanskrit": word["word_sanskrit"], "transliteration": word.get("word_transliteration"),
            "meaning": word["meaning_en"], "grammaticalInfo": None,
        })

    def add_question(lesson_id, source_id, qtype, prompt, explanation, points, order, metadata, options, answer):
        question_id = oid("quiz_question", str(source_id))
        records["quizQuestions"].append({
            "id": question_id, "quizId": quiz_id_by_lesson[lesson_id], "type": qtype,
            "question": prompt, "explanation": explanation, "points": points,
            "order": order, "metadata": json.dumps(metadata, ensure_ascii=False),
        })
        for index, option in enumerate(options if isinstance(options, list) else [], start=1):
            value = option if isinstance(option, str) else json.dumps(option, ensure_ascii=False)
            records["quizOptions"].append({
                "id": oid("quiz_option", f"{source_id}:{index}"), "questionId": question_id,
                "value": value, "label": value,
                "isCorrect": isinstance(answer, str) and value.strip().casefold() == answer.strip().casefold(),
                "explanation": None, "order": index,
            })

    quiz_id_by_lesson = {}
    for lesson in records["lessons"]:
        lesson_id = lesson["id"]
        quiz_id = oid("quiz", lesson["slug"])
        quiz_id_by_lesson[lesson_id] = quiz_id
        records["quizzes"].append({
            "id": quiz_id, "lessonId": lesson_id, "title": f"{lesson['title']} Quiz",
            "description": lesson.get("description"), "passingScore": None,
            "maxAttempts": None, "createdAt": NOW, "updatedAt": NOW,
        })

    question_order = defaultdict(int)
    type_map = {
        "match_pairs": "MATCHING", "word_order": "ORDERING",
        "fill_blank": "FILL_BLANK", "true_false": "TRUE_FALSE",
    }
    for question in questions:
        key = question["verse_key"]
        lesson_id = lesson_id_by_verse[key]
        question_order[lesson_id] += 1
        options = json.loads(question["options_json"])
        answer = json.loads(question["correct_answer_json"])
        add_question(
            lesson_id, f"verse-question:{question['id']}",
            type_map.get(question["question_type"], "MULTIPLE_CHOICE"),
            question["prompt"], question["explanation"], question["xp_points"],
            question_order[lesson_id], {
                "sourceQuestionId": question["id"], "verseKey": key,
                "questionType": question["question_type"], "lessonLevel": question["lesson_level"],
                "instruction": question["instruction"], "sourceQuestionOrder": question["question_order"],
                "difficulty": question["difficulty"], "promptSanskrit": question["prompt_sanskrit"],
                "hint": question["hint"], "options": options, "correctAnswer": answer,
            }, options, answer,
        )

    for section in curriculum["sections"]:
        lesson_id = thematic_first_lesson[section["id"]]
        for item in section.get("questions", []):
            question_order[lesson_id] += 1
            add_question(
                lesson_id, f"thematic-question:{item['id']}",
                "TRUE_FALSE" if item.get("type") == "true_false" else "MULTIPLE_CHOICE",
                item["prompt"], item.get("explanation"), 10, question_order[lesson_id], {
                    "sourceQuestionId": item["id"], "sourceType": item.get("type"),
                    "verseReference": item.get("verse_reference"),
                    "difficulty": item.get("difficulty"),
                }, item.get("options", []), item.get("correct_answer"),
            )

    result = {
        "schema_version": "prisma-content-seed-v2",
        "source_course_id": curriculum["course_id"], "generated_at": NOW,
        "notes": [
            "Hierarchy: Scripture -> Chapter -> Module -> Lesson -> Verse.",
            "Every Verse has one lessonId and no chapterId. Theme-owned verses are assigned to the first matching theme; overlapping references remain in question metadata.",
            "Each theme spanning source chapters is split into one lesson per chapter to satisfy unique lessonId/verseNumber constraints.",
            "Chapter numbers and source verse keys are retained as verseKey metadata; verseKey is an additive optional field for the supplied Prisma Verse model.",
            "Question level, original question type, answer, options, hints, and references are preserved in QuizQuestion.metadata and QuizOption rows.",
            "User and progress models are runtime application data and are not included in this content seed.",
        ],
        "records": dict(records), "thematic_curriculum": curriculum,
        "counts": {name: len(rows) for name, rows in records.items()},
    }
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote Prisma content seed: {OUT_PATH}")
    print(json.dumps(result["counts"], indent=2))


if __name__ == "__main__":
    main()
