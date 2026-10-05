"""Idempotently load the GitaLingo SQLite corpus into MongoDB Atlas.

Set MONGODB_URI in the environment before running this script. The target
database defaults to ``gita_duolingo`` and can be overridden with
MONGODB_DATABASE. Existing documents with matching IDs are updated; unrelated
documents and collections are left untouched.
"""

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Iterable

BASE_DIR = Path(__file__).resolve().parents[1]
LOCAL_DRIVER_DIR = BASE_DIR / ".mongo_runtime"
if LOCAL_DRIVER_DIR.exists():
    sys.path.insert(0, str(LOCAL_DRIVER_DIR))


def rows_as_dicts(conn: sqlite3.Connection, query: str) -> list[dict]:
    return [dict(row) for row in conn.execute(query).fetchall()]


def upsert_documents(collection, documents: Iterable[dict], id_field: str) -> int:
    from pymongo import ReplaceOne

    batch = []
    written = 0
    for document in documents:
        doc = dict(document)
        doc["_id"] = doc[id_field]
        batch.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
        if len(batch) >= 500:
            result = collection.bulk_write(batch, ordered=False)
            written += result.upserted_count + result.modified_count
            batch.clear()
    if batch:
        result = collection.bulk_write(batch, ordered=False)
        written += result.upserted_count + result.modified_count
    return written


def main() -> None:
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise SystemExit("Set MONGODB_URI in the environment before running this importer.")

    try:
        from pymongo import MongoClient
    except ImportError as exc:
        raise SystemExit(
            "MongoDB driver missing. Install it with: "
            "python -m pip install 'pymongo[srv]'"
        ) from exc

    db_path = BASE_DIR / "database" / "gita_duolingo.db"
    curriculum_path = BASE_DIR / "data" / "curriculum.json"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    client = MongoClient(uri, serverSelectionTimeoutMS=20000)

    try:
        client.admin.command("ping")
        database = client[os.environ.get("MONGODB_DATABASE", "gita_duolingo")]

        chapters = rows_as_dicts(conn, "SELECT * FROM chapters ORDER BY chapter_number")
        verses = rows_as_dicts(conn, "SELECT * FROM verses ORDER BY chapter_number, verse_number")
        for verse in verses:
            verse["meaning"] = verse.get("meaning_en")
        vocabulary = rows_as_dicts(conn, "SELECT * FROM vocabulary ORDER BY verse_key, id")
        questions = rows_as_dicts(
            conn,
            "SELECT * FROM questions ORDER BY chapter_number, verse_number, question_order",
        )
        lessons = rows_as_dicts(conn, "SELECT * FROM lessons ORDER BY verse_key, lesson_number")

        for question in questions:
            question["options"] = json.loads(question.pop("options_json"))
            question["correct_answer"] = json.loads(question.pop("correct_answer_json"))

        curriculum = json.loads(curriculum_path.read_text(encoding="utf-8"))
        course_id = curriculum["course_id"]
        sections = []
        curriculum_questions = []
        for section in curriculum["sections"]:
            section_doc = {key: value for key, value in section.items() if key != "questions"}
            section_doc["course_id"] = course_id
            section_doc["question_count"] = len(section["questions"])
            sections.append(section_doc)
            for question in section["questions"]:
                curriculum_questions.append({
                    **question,
                    "course_id": course_id,
                    "section_id": section["id"],
                })

        collections = {
            "chapters": (chapters, "chapter_number"),
            "verses": (verses, "verse_key"),
            "vocabulary": (vocabulary, "id"),
            "questions": (questions, "id"),
            "lessons": (lessons, "id"),
            "curriculum": ([curriculum], "course_id"),
            "sections": (sections, "id"),
            "curriculum_questions": (curriculum_questions, "id"),
        }

        for name, (documents, id_field) in collections.items():
            written = upsert_documents(database[name], documents, id_field)
            print(f"{name}: {len(documents)} source documents, {written} inserted or updated")

        database["verses"].create_index("chapter_number")
        database["vocabulary"].create_index("verse_key")
        database["questions"].create_index([("verse_key", 1), ("question_order", 1)])
        database["questions"].create_index([("chapter_number", 1), ("verse_number", 1)])
        database["lessons"].create_index([("verse_key", 1), ("lesson_number", 1)])
        database["sections"].create_index([("course_id", 1), ("order", 1)])
        database["curriculum_questions"].create_index([("section_id", 1), ("id", 1)])

        expected = {name: len(records) for name, (records, _) in collections.items()}
        actual = {name: database[name].count_documents({}) for name in collections}
        print(f"database: {database.name}")
        print(f"verified counts: {actual}")
        for name, count in expected.items():
            if actual[name] < count:
                raise RuntimeError(f"Verification failed for {name}: expected at least {count}, got {actual[name]}")
    finally:
        conn.close()
        client.close()


if __name__ == "__main__":
    main()
