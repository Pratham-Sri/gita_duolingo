"""Load the Prisma-shaped content seed into an isolated MongoDB database."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DRIVER_DIR = ROOT / ".mongo_runtime"
if DRIVER_DIR.exists():
    sys.path.insert(0, str(DRIVER_DIR))

SEED_PATH = ROOT / "exports" / "prisma_seed_content.json"
ID_FIELDS = {
    "id", "scriptureId", "chapterId", "moduleId", "lessonId", "verseId",
    "quizId", "questionId",
}


FIELD_MAPS = {
    "scriptures": {"coverImage": "cover_image", "totalChapters": "total_chapters", "createdAt": "created_at", "updatedAt": "updated_at"},
    "scriptureTranslations": {"scriptureId": "scripture_id"},
    "chapters": {"scriptureId": "scripture_id", "createdAt": "created_at", "updatedAt": "updated_at"},
    "chapterTranslations": {"chapterId": "chapter_id"},
    "modules": {"chapterId": "chapter_id", "createdAt": "created_at", "updatedAt": "updated_at"},
    "moduleTranslations": {"moduleId": "module_id"},
    "lessons": {"moduleId": "module_id", "estimatedMinutes": "estimated_minutes", "xpReward": "xp_reward", "createdAt": "created_at", "updatedAt": "updated_at"},
    "lessonTranslations": {"lessonId": "lesson_id"},
    "lessonContentBlocks": {"lessonId": "lesson_id"},
    "verses": {"chapterId": "chapter_id", "verseNumber": "verse_number", "audioUrl": "audio_url", "commentarySummary": "commentary_summary", "createdAt": "created_at", "updatedAt": "updated_at"},
    "verseTranslations": {"verseId": "verse_id", "createdAt": "created_at", "updatedAt": "updated_at"},
    "verseWords": {"verseId": "verse_id", "grammaticalInfo": "grammatical_info"},
    "lessonVerses": {"lessonId": "lesson_id", "verseId": "verse_id"},
    "quizzes": {"lessonId": "lesson_id", "passingScore": "passing_score", "maxAttempts": "max_attempts", "createdAt": "created_at", "updatedAt": "updated_at"},
    "quizQuestions": {"quizId": "quiz_id"},
    "quizOptions": {"questionId": "question_id", "isCorrect": "is_correct"},
}


def prepare_document(source, object_id_type, model_name):
    document = dict(source)
    for key in ID_FIELDS:
        value = document.get(key)
        if isinstance(value, str) and len(value) == 24:
            document[key] = object_id_type(value)
    field_map = FIELD_MAPS[model_name]
    mapped = {}
    for key, value in document.items():
        new_key = field_map.get(key, key)
        if key.endswith("At") and isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        mapped[new_key] = value
    mapped["_id"] = mapped.pop("id")
    return mapped


def main():
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise SystemExit("Set MONGODB_URI in the environment before running this uploader.")

    from bson import ObjectId
    from pymongo import MongoClient, ReplaceOne

    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    database_name = os.environ.get("MONGODB_PRISMA_DATABASE", "gita_duolingo_prisma")
    client = MongoClient(uri, serverSelectionTimeoutMS=20000)
    try:
        client.admin.command("ping")
        db = client[database_name]
        actual_counts = {}
        collection_names = {
            "scriptures", "scripture_translations", "chapters", "chapter_translations",
            "modules", "module_translations", "lessons", "lesson_translations",
            "lesson_content_blocks", "verses", "verse_translations", "verse_words",
            "lesson_verses", "quizzes", "quiz_questions", "quiz_options",
        }
        # Replace documents from the previous seed version, whose string IDs
        # were not valid BSON ObjectIds. This database is reserved for this seed.
        for collection_name in collection_names:
            db[collection_name].delete_many({"_id": {"$regex": r"^[0-9a-f]{32}$"}})
        for model_name, records in payload["records"].items():
            collection_name = {
                "scriptureTranslations": "scripture_translations",
                "chapterTranslations": "chapter_translations",
                "moduleTranslations": "module_translations",
                "lessonTranslations": "lesson_translations",
                "lessonContentBlocks": "lesson_content_blocks",
                "verseTranslations": "verse_translations",
                "verseWords": "verse_words",
                "lessonVerses": "lesson_verses",
                "quizQuestions": "quiz_questions",
                "quizOptions": "quiz_options",
            }.get(model_name, model_name)
            collection = db[collection_name]
            prepared = [prepare_document(record, ObjectId, model_name) for record in records]
            for start in range(0, len(prepared), 500):
                batch = prepared[start:start + 500]
                if batch:
                    collection.bulk_write(
                        [ReplaceOne({"_id": doc["_id"]}, doc, upsert=True) for doc in batch],
                        ordered=False,
                    )
            count = collection.count_documents({})
            actual_counts[collection_name] = count
            if count < len(records):
                raise RuntimeError(
                    f"{collection_name}: expected at least {len(records)} documents, found {count}"
                )

        # Clean up obsolete duplicate Hindi rows from earlier seed versions,
        # only where the same verse now has the canonical CONTEMPORARY row.
        verse_translation_docs = payload["records"]["verseTranslations"]
        hindi_verse_ids = [
            ObjectId(doc["verseId"]) for doc in verse_translation_docs
            if doc["language"] == "hi" and doc["type"] == "CONTEMPORARY"
        ]
        if hindi_verse_ids:
            db["verse_translations"].delete_many({
                "language": "hi", "type": "LITERAL", "verse_id": {"$in": hindi_verse_ids},
            })
        actual_counts["verse_translations"] = db["verse_translations"].count_documents({})

        # Mirror the unique relations and lookup indexes from the provided model.
        index_specs = {
            "scriptures": [([("slug", 1)], {"unique": True})],
            "scripture_translations": [([("scripture_id", 1), ("language", 1)], {"unique": True})],
            "chapters": [([("scripture_id", 1), ("number", 1)], {"unique": True}), ([ ("scripture_id", 1), ("slug", 1)], {"unique": True}), ([ ("scripture_id", 1), ("order", 1)], {})],
            "chapter_translations": [([("chapter_id", 1), ("language", 1)], {"unique": True})],
            "modules": [([("chapter_id", 1), ("slug", 1)], {"unique": True}), ([ ("chapter_id", 1), ("order", 1)], {"unique": True})],
            "module_translations": [([("module_id", 1), ("language", 1)], {"unique": True})],
            "lessons": [([("module_id", 1), ("slug", 1)], {"unique": True}), ([ ("module_id", 1), ("order", 1)], {"unique": True})],
            "lesson_translations": [([("lesson_id", 1), ("language", 1)], {"unique": True})],
            "lesson_content_blocks": [([("lesson_id", 1), ("order", 1)], {"unique": True})],
            "verses": [([("chapter_id", 1), ("verse_number", 1)], {"unique": True})],
            "verse_translations": [([("verse_id", 1), ("language", 1), ("type", 1)], {"unique": True})],
            "verse_words": [([("verse_id", 1), ("position", 1)], {"unique": True})],
            "lesson_verses": [([("lesson_id", 1), ("verse_id", 1)], {"unique": True}), ([ ("lesson_id", 1), ("order", 1)], {"unique": True})],
            "quizzes": [([("lesson_id", 1)], {"unique": True})],
            "quiz_questions": [([("quiz_id", 1), ("order", 1)], {"unique": True})],
            "quiz_options": [([("question_id", 1), ("order", 1)], {"unique": True})],
        }
        for collection_name, specs in index_specs.items():
            for keys, options in specs:
                db[collection_name].create_index(keys, **options)

        print(f"database: {database_name}")
        print(f"verified collection counts: {json.dumps(actual_counts, sort_keys=True)}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
