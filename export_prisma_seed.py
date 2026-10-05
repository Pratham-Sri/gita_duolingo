"""Export the Gita content as deterministic seed documents for the app Prisma models.

The generated JSON contains content records only. Authentication, user preferences,
progress, attempts, XP, streaks, and achievements are runtime application data.
"""

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "gita_duolingo.db"
OUT_PATH = ROOT / "exports" / "prisma_seed_content.json"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def oid(kind: str, key: str) -> str:
    """Return a stable 24-character ID compatible with ObjectId-shaped schemas."""
    return hashlib.md5(f"gitalingo:{kind}:{key}".encode("utf-8")).hexdigest()


def read_rows(conn, sql, args=()):
    return [dict(row) for row in conn.execute(sql, args).fetchall()]


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
    curriculum_path = ROOT / "data" / "curriculum.json"
    curriculum = json.loads(curriculum_path.read_text(encoding="utf-8"))
    conn.close()

    scripture_id = oid("scripture", "bhagavad-gita")
    scripture = [{
        "id": scripture_id, "slug": "bhagavad-gita", "title": "Bhagavad Gita",
        "description": "The Bhagavad Gita, organized as a structured Sanskrit learning course.",
        "author": None, "tradition": "Hindu", "coverImage": None,
        "status": "PUBLISHED", "totalChapters": len(chapters),
        "createdAt": NOW, "updatedAt": NOW,
    }]
    scripture_translations = [{
        "id": oid("scripture_translation", "bhagavad-gita:en"), "scriptureId": scripture_id,
        "language": "en", "title": "Bhagavad Gita",
        "description": "A thematic and verse-by-verse learning course.",
    }]

    chapter_docs, chapter_translations, module_docs, module_translations = [], [], [], []
    lesson_docs, lesson_translations, content_blocks, verse_docs = [], [], [], []
    verse_translations, verse_words, lesson_verses = [], [], []
    quiz_docs, quiz_questions, quiz_options = [], [], []
    chapter_id_by_num, module_id_by_num, verse_id_by_key = {}, {}, {}
    lesson_id_by_stage = {}

    for ch in chapters:
        n = ch["chapter_number"]
        chapter_id = oid("chapter", str(n))
        module_id = oid("module", str(n))
        chapter_id_by_num[n] = chapter_id
        module_id_by_num[n] = module_id
        chapter_docs.append({
            "id": chapter_id, "scriptureId": scripture_id, "number": n,
            "slug": f"chapter-{n}", "title": ch["name_transliterated"] or f"Chapter {n}",
            "description": ch.get("summary_en"), "difficulty": "BEGINNER",
            "status": "PUBLISHED", "order": n,
            "createdAt": NOW, "updatedAt": NOW,
        })
        chapter_translations.append({
            "id": oid("chapter_translation", f"{n}:en"), "chapterId": chapter_id,
            "language": "en", "title": ch["name_meaning"] or f"Chapter {n}",
            "description": ch.get("summary_en"),
        })
        module_docs.append({
            "id": module_id, "chapterId": chapter_id, "slug": f"chapter-{n}-lessons",
            "title": ch["name_meaning"] or f"Chapter {n}",
            "description": f"Verse lessons for Chapter {n} of the Bhagavad Gita.",
            "order": 1, "status": "PUBLISHED", "createdAt": NOW, "updatedAt": NOW,
        })
        module_translations.append({
            "id": oid("module_translation", f"{n}:en"), "moduleId": module_id,
            "language": "en", "title": ch["name_meaning"] or f"Chapter {n}",
            "description": f"Learn the verses of Chapter {n}.",
        })

    for v in verses:
        key = v["verse_key"]
        vid = oid("verse", key)
        verse_id_by_key[key] = vid
        verse_docs.append({
            "id": vid, "chapterId": chapter_id_by_num[v["chapter_number"]],
            "verseNumber": v["verse_number"], "sanskrit": v["text_devanagari"],
            "transliteration": v["transliteration"], "audioUrl": None,
            "createdAt": NOW, "updatedAt": NOW,
        })
        for lang, kind, value, source in (
            ("en", "CONTEMPORARY", v.get("translation_en"), v.get("translation_source")),
            ("en", "PRACTICAL", v.get("meaning_en"), "GitaLingo contextual learning meaning"),
            ("hi", "LITERAL", v.get("translation_hi"), None),
        ):
            if value:
                verse_translations.append({
                    "id": oid("verse_translation", f"{key}:{lang}:{kind}"),
                    "verseId": vid, "language": lang, "type": kind,
                    "content": value, "source": source, "author": None,
                    "createdAt": NOW, "updatedAt": NOW,
                })

    word_positions = {}
    for w in words:
        key = w["verse_key"]
        word_positions[key] = word_positions.get(key, 0) + 1
        verse_words.append({
            "id": oid("verse_word", f"{key}:{w['id']}"), "verseId": verse_id_by_key[key],
            "position": word_positions[key],
            "sanskrit": w["word_sanskrit"], "transliteration": w.get("word_transliteration"),
            "meaning": w["meaning_en"], "grammaticalInfo": None,
        })

    # Four chapter-level learning stages. Each stage lesson links to every verse
    # in the chapter; each verse question is assigned to its original stage.
    lesson_titles = {
        1: ("Sanskrit Words", "Build vocabulary from the chapter's verses."),
        2: ("Verse Structure", "Practice verse flow, recitation, and sentence structure."),
        3: ("Meaning and Context", "Understand translations, speakers, and dialogue context."),
        4: ("Wisdom in Practice", "Apply philosophical ideas to choices and daily life."),
    }
    for ch in chapters:
        n = ch["chapter_number"]
        chapter_verses = [v for v in verses if v["chapter_number"] == n]
        for stage, (title, description) in lesson_titles.items():
            lesson_id = oid("lesson", f"chapter:{n}:stage:{stage}")
            lesson_id_by_stage[(n, stage)] = lesson_id
            lesson_docs.append({
                "id": lesson_id, "moduleId": module_id_by_num[n],
                "slug": f"chapter-{n}-stage-{stage}", "title": title,
                "description": description, "order": stage, "estimatedMinutes": None,
                "difficulty": ("BEGINNER" if stage == 1 else "INTERMEDIATE" if stage < 4 else "ADVANCED"),
                "xpReward": 50, "status": "PUBLISHED", "createdAt": NOW, "updatedAt": NOW,
            })
            lesson_translations.append({
                "id": oid("lesson_translation", f"{n}:{stage}:en"), "lessonId": lesson_id,
                "language": "en", "title": title, "description": description,
            })
            content_blocks.extend([
                {"id": oid("content_block", f"{n}:{stage}:intro"), "lessonId": lesson_id,
                 "type": "INTRO", "order": 1, "title": title, "content": description, "metadata": None},
                {"id": oid("content_block", f"{n}:{stage}:summary"), "lessonId": lesson_id,
                 "type": "SUMMARY", "order": 2, "title": "Learning goal", "content": description, "metadata": None},
            ])
            for order, v in enumerate(chapter_verses, start=1):
                lesson_verses.append({
                    "id": oid("lesson_verse", f"{n}:{stage}:{v['verse_key']}"),
                    "lessonId": lesson_id, "verseId": verse_id_by_key[v["verse_key"]], "order": order,
                })

            quiz_id = oid("quiz", f"chapter:{n}:stage:{stage}")
            quiz_docs.append({
                "id": quiz_id, "lessonId": lesson_id, "title": f"{title} Quiz",
                "description": f"Practice {title.lower()} in Chapter {n}.",
                "passingScore": None, "maxAttempts": None, "createdAt": NOW, "updatedAt": NOW,
            })
            stage_questions = [q for q in questions if q["chapter_number"] == n and q["lesson_level"] == stage]
            for question_order, q in enumerate(stage_questions, start=1):
                qid = oid("quiz_question", str(q["id"]))
                raw_options = json.loads(q["options_json"])
                answer = json.loads(q["correct_answer_json"])
                type_map = {
                    "match_pairs": "MATCHING", "word_order": "ORDERING",
                    "fill_blank": "FILL_BLANK", "true_false": "TRUE_FALSE",
                }
                qtype = type_map.get(q["question_type"], "MULTIPLE_CHOICE")
                quiz_questions.append({
                    "id": qid, "quizId": quiz_id, "type": qtype,
                    "question": q["prompt"], "explanation": q["explanation"],
                    "points": q["xp_points"], "order": question_order,
                    "metadata": json.dumps({
                        "sourceQuestionId": q["id"], "verseKey": q["verse_key"],
                        "questionType": q["question_type"], "instruction": q["instruction"],
                        "sourceQuestionOrder": q["question_order"],
                        "promptSanskrit": q["prompt_sanskrit"], "hint": q["hint"],
                        "options": raw_options, "correctAnswer": answer,
                    }, ensure_ascii=False),
                })
                option_values = raw_options if isinstance(raw_options, list) else []
                for index, option in enumerate(option_values, start=1):
                    value = option if isinstance(option, str) else json.dumps(option, ensure_ascii=False)
                    quiz_options.append({
                        "id": oid("quiz_option", f"{q['id']}:{index}"), "questionId": qid,
                        "value": value, "label": value,
                        "isCorrect": isinstance(answer, str) and value.strip().casefold() == answer.strip().casefold(),
                        "explanation": None, "order": index,
                    })

    # The requested Duolingo themes are cross-chapter in some cases. Anchor
    # each Module to its first chapter and use LessonVerse for its full coverage.
    chapter_module_orders = {ch["chapter_number"]: 2 for ch in chapters}
    verse_by_number = {(v["chapter_number"], v["verse_number"]): v for v in verses}
    for section in curriculum["sections"]:
        anchor_chapter = (section.get("chapter_numbers") or [])[0]
        if not anchor_chapter:
            continue
        module_id = oid("thematic_module", section["id"])
        lesson_id = oid("thematic_lesson", section["id"])
        module_order = chapter_module_orders[anchor_chapter]
        chapter_module_orders[anchor_chapter] += 1
        module_docs.append({
            "id": module_id, "chapterId": chapter_id_by_num[anchor_chapter],
            "slug": f"theme-{section['id']}", "title": section["title"],
            "description": section["description"], "order": module_order,
            "status": "PUBLISHED", "createdAt": NOW, "updatedAt": NOW,
        })
        module_translations.append({
            "id": oid("thematic_module_translation", f"{section['id']}:en"),
            "moduleId": module_id, "language": "en", "title": section["title"],
            "description": section["description"],
        })
        lesson_docs.append({
            "id": lesson_id, "moduleId": module_id, "slug": f"{section['id']}-lesson",
            "title": section["subtitle"], "description": section["description"],
            "order": 1, "estimatedMinutes": None, "difficulty": "BEGINNER",
            "xpReward": 50, "status": "PUBLISHED", "createdAt": NOW, "updatedAt": NOW,
        })
        lesson_translations.append({
            "id": oid("thematic_lesson_translation", f"{section['id']}:en"),
            "lessonId": lesson_id, "language": "en", "title": section["subtitle"],
            "description": section["description"],
        })
        content_blocks.extend([
            {"id": oid("thematic_content", f"{section['id']}:intro"), "lessonId": lesson_id,
             "type": "INTRO", "order": 1, "title": section["title"],
             "content": section["description"], "metadata": json.dumps({"learningObjectives": section.get("learning_objectives", [])}, ensure_ascii=False)},
            {"id": oid("thematic_content", f"{section['id']}:takeaway"), "lessonId": lesson_id,
             "type": "KEY_TAKEAWAY", "order": 2, "title": "Learning objectives",
             "content": "\n".join(f"• {item}" for item in section.get("learning_objectives", [])),
             "metadata": json.dumps({"sectionId": section["id"], "verseRanges": section.get("verse_ranges", [])}, ensure_ascii=False)},
        ])
        linked_keys = set()
        for verse_range in section.get("verse_ranges", []):
            start = verse_range.get("start", "")
            end = verse_range.get("end", start)
            start_match = re.fullmatch(r"BG(\d+)\.(\d+)", start)
            end_match = re.fullmatch(r"BG(\d+)\.(\d+)", end)
            if not start_match or not end_match:
                continue
            start_ch, start_v = map(int, start_match.groups())
            end_ch, end_v = map(int, end_match.groups())
            for chapter_number in range(start_ch, end_ch + 1):
                lo = start_v if chapter_number == start_ch else 1
                hi = end_v if chapter_number == end_ch else max(
                    (v["verse_number"] for v in verses if v["chapter_number"] == chapter_number), default=0
                )
                for verse_number in range(lo, hi + 1):
                    v = verse_by_number.get((chapter_number, verse_number))
                    if v:
                        linked_keys.add(v["verse_key"])
        for order, key in enumerate(sorted(linked_keys, key=lambda k: tuple(map(int, k[2:].split(".")))), start=1):
            lesson_verses.append({
                "id": oid("thematic_lesson_verse", f"{section['id']}:{key}"),
                "lessonId": lesson_id, "verseId": verse_id_by_key[key], "order": order,
            })

        quiz_id = oid("thematic_quiz", section["id"])
        quiz_docs.append({
            "id": quiz_id, "lessonId": lesson_id, "title": f"{section['title']} Quiz",
            "description": section["description"], "passingScore": None,
            "maxAttempts": None, "createdAt": NOW, "updatedAt": NOW,
        })
        for question_order, q in enumerate(section.get("questions", []), start=1):
            qid = oid("thematic_quiz_question", q["id"])
            original_type = q.get("type", "multiple_choice")
            qtype = "TRUE_FALSE" if original_type == "true_false" else "MULTIPLE_CHOICE"
            options = q.get("options", [])
            answer = q.get("correct_answer")
            quiz_questions.append({
                "id": qid, "quizId": quiz_id, "type": qtype,
                "question": q["prompt"], "explanation": q.get("explanation"),
                "points": 10, "order": question_order,
                "metadata": json.dumps({
                    "sourceQuestionId": q["id"], "sourceType": original_type,
                    "verseReference": q.get("verse_reference"),
                    "difficulty": q.get("difficulty"),
                }, ensure_ascii=False),
            })
            for index, option in enumerate(options, start=1):
                value = str(option)
                quiz_options.append({
                    "id": oid("thematic_quiz_option", f"{q['id']}:{index}"),
                    "questionId": qid, "value": value, "label": value,
                    "isCorrect": value.strip().casefold() == str(answer).strip().casefold(),
                    "explanation": None, "order": index,
                })

    # Preserve the original thematic course as a companion payload because its
    # sections can span chapters while the supplied Module model belongs to one.
    result = {
        "schema_version": "prisma-content-seed-v1",
        "source_course_id": curriculum["course_id"],
        "generated_at": NOW,
        "notes": [
            "Only scripture/course content is seeded; user/runtime models are intentionally empty.",
            "The separate thematic curriculum is preserved in thematic_curriculum.json because sections can cross chapter boundaries.",
            "Question metadata preserves source question types, options, answers, hints, and verse references for types not represented directly by the app enum.",
        ],
        "records": {
            "scriptures": scripture, "scriptureTranslations": scripture_translations,
            "chapters": chapter_docs, "chapterTranslations": chapter_translations,
            "modules": module_docs, "moduleTranslations": module_translations,
            "lessons": lesson_docs, "lessonTranslations": lesson_translations,
            "lessonContentBlocks": content_blocks, "verses": verse_docs,
            "verseTranslations": verse_translations, "verseWords": verse_words,
            "lessonVerses": lesson_verses, "quizzes": quiz_docs,
            "quizQuestions": quiz_questions, "quizOptions": quiz_options,
        },
        "thematic_curriculum": curriculum,
        "counts": {},
    }
    result["counts"] = {name: len(rows) for name, rows in result["records"].items()}
    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote Prisma content seed: {OUT_PATH}")
    print(json.dumps(result["counts"], indent=2))


if __name__ == "__main__":
    main()
