# GitaLingo Data Schema for Application Developers

This document describes the data model and the supported ways to load it into a client application. The source of truth is the SQLite database `gita_duolingo.db`; JSON exports and the MongoDB collections are derived from it.

## Corpus at a glance

- Course: `bhagavad-gita-foundations`
- Chapters: 18
- Verse records: 701 (the source numbering includes BG 13.1; editions that omit this verse commonly report 700)
- Verse-level quiz questions: 9,119
- Vocabulary rows: 12,681
- Per-verse lesson paths: 2,804
- Thematic curriculum: 10 ordered sections, with questions independent of the verse-level quiz bank
- All verse records have `meaning_en`; meanings are generated learning explanations of 50–60 words. `translation_en` is the underlying English translation and must not be confused with this contextual meaning.

## Files to consume

| File | Use |
|---|---|
| `data/curriculum.json` | Recommended import for the themed Duolingo-style course: sections, objectives, references, and section questions. |
| `exports/verses.json` | Verse records with identifiers, Sanskrit, transliteration, translation, meaning, speaker, and attribution. |
| `exports/questions.json` | Flat verse-linked question bank. |
| `exports/gita_duolingo_bundle.json` | Offline-friendly object keyed by `verse_key`, each with a verse and its questions. |
| `exports/chapters.json` | Chapter metadata. |
| `exports/gita_duolingo.sql` | SQL import/export representation. |
| `gita_duolingo.db` | SQLite database. |
| `structure_metadata.json` | Counts and per-chapter structural summary for analysis. |

The curriculum and verse-level quiz bank are two different learning experiences. Use `data/curriculum.json` for thematic sections such as “Arjuna's Grief” and “The Eternal Soul.” Use the verse bundle when the app teaches one shloka at a time.

## Relational model

### `chapters`

One record per chapter; primary key `id`, unique natural key `chapter_number` (1–18).

| Field | Type | Meaning |
|---|---|---|
| `id` | integer | Source/database identifier. |
| `chapter_number` | integer | Chapter number; stable join key. |
| `name_sanskrit` | string | Sanskrit chapter name. |
| `name_transliterated` | string | Romanized chapter name. |
| `name_meaning` | string | English chapter title/meaning. |
| `summary_en`, `summary_hi` | string/null | Chapter summaries. |
| `verses_count` | integer | Source-reported verse count. |
| `slug` | string/null | Source slug. |

### `verses`

One record per shloka. Join to chapters by `chapter_number`; use `verse_key` as the portable identifier (for example, `BG2.47`).

| Field | Type | Meaning |
|---|---|---|
| `id` | integer | Database identifier. |
| `chapter_number`, `verse_number` | integer | Numeric location. |
| `verse_key` | string | Stable application key, e.g. `BG2.47`; unique. |
| `text_devanagari` | string | Sanskrit verse in Devanagari. |
| `transliteration` | string | Roman transliteration. |
| `word_meanings_raw` | string/null | Source word-by-word gloss, if available. |
| `translation_en` | string | English translation of the verse. |
| `translation_hi` | string/null | Hindi translation, when available. |
| `translation_source` | string/null | Translation attribution/source. Preserve when displaying or redistributing. |
| `meaning_en` | string | 50–60 word learner-oriented contextual explanation. |
| `speaker` | string | Speaker label inferred from the verse. |
| `commentary_summary` | string/null | Reserved optional commentary field. |

The API also returns `meaning` as an alias of `meaning_en`. MongoDB verse documents contain both `meaning_en` and `meaning` for compatibility.

### `vocabulary`

One row per Sanskrit term/gloss attached to a verse.

| Field | Type | Meaning |
|---|---|---|
| `id` | integer | Row identifier. |
| `verse_id` | integer | Foreign key to `verses.id`. |
| `verse_key` | string | Portable verse identifier. |
| `word_sanskrit` | string | Sanskrit token. |
| `word_transliteration` | string/null | Transliteration where available. |
| `meaning_en` | string | English gloss. |

### `questions`

Verse-linked quiz items. `lesson_level` gives the learning stage; `question_order` sorts questions within a verse.

| Field | Type | Meaning |
|---|---|---|
| `id` | integer | Question identifier. |
| `verse_id`, `verse_key` | integer/string | Verse reference. |
| `chapter_number`, `verse_number` | integer | Numeric location. |
| `lesson_level` | integer | 1 vocabulary, 2 verse structure, 3 meaning/context, 4 philosophical application. |
| `question_order` | integer | Display order for this verse. |
| `question_type` | string | Interaction/answer shape; see below. |
| `difficulty` | enum | `beginner`, `intermediate`, or `advanced`. |
| `instruction` | string | Short UI instruction. |
| `prompt` | string | Question text. |
| `prompt_sanskrit` | string/null | Optional Sanskrit text shown with the prompt. |
| `options` | JSON value | Choices, matching pairs, or other type-specific option data. SQLite stores this as `options_json`; JSON exports/API decode it. |
| `correct_answer` | JSON value | Correct response, with type-dependent shape. SQLite stores `correct_answer_json`; JSON exports/API decode it. |
| `explanation` | string | Feedback/explanation after answering. |
| `hint` | string/null | Optional hint. |
| `xp_points` | integer | XP reward for a correct answer. |

Known verse-level `question_type` values include `match_pairs`, `mcq_vocab`, `mcq_reverse_vocab`, `transliteration_match`, `fill_blank`, `word_order`, `speaker_context`, `translation_mcq`, `true_false`, `philosophical_insight`, `life_scenario`, `metaphor`, and `takeaway`. Build renderers with a fallback because new types may be added.

For ordinary choice questions, `options` is an array of strings and `correct_answer` is a string. For `word_order`, the answer is an ordered value; for `match_pairs`, it is a mapping/object. Do not assume every answer is a string.

**Answer privacy:** exported question records include `correct_answer` for trusted/offline use. Do not send this property to an untrusted client before the learner submits an answer. In a client/server app, serve a safe question DTO without the answer and validate submissions server-side.

### `lessons`

Four learning paths per verse, ordered by `lesson_number` (1–4). Fields: `id`, `verse_key`, `lesson_number`, `title`, `description`, and `total_xp`.

## Thematic curriculum JSON shape

`data/curriculum.json` has `schema_version`, `course_id`, `title`, `language`, `description`, and an ordered `sections` array. Each section contains:

- `id` (stable string), `order`, `title`, `subtitle`, `description`
- `chapter_numbers`: chapters relevant to the section
- `verse_ranges`: one or more `{ "start": "BG2.11", "end": "BG2.30" }` references
- `learning_objectives`: strings
- `questions`: section-specific learning questions

Each thematic question has `id`, `type`, `prompt`, `options`, `correct_answer`, `explanation`, `verse_reference`, and `difficulty`. Thematic question types currently include `multiple_choice`, `true_false`, and `scenario`. IDs are strings and stable; do not parse them as integers. `verse_reference` can identify a single verse or a range.

## MongoDB layout

Database name: `gita_duolingo`. Collections:

| Collection | `_id` | Document shape |
|---|---|---|
| `chapters` | `chapter_number` | Chapter row fields. |
| `verses` | `verse_key` | Verse fields plus `meaning` alias. |
| `vocabulary` | `id` | Vocabulary row fields. |
| `questions` | `id` | Question fields, with decoded `options` and `correct_answer`. |
| `lessons` | `id` | Lesson path fields. |
| `curriculum` | `course_id` | Whole thematic curriculum document. |
| `sections` | section `id` | Section metadata without embedded questions, plus `course_id` and `question_count`. |
| `curriculum_questions` | question `id` | Thematic question fields plus `course_id` and `section_id`. |

## App Prisma model seed

The supplied application requirement uses the hierarchy `Scripture → Chapter → Module → Lesson → Quiz → QuizQuestion/QuizOption`, with verse and translation tables attached alongside it. Run:

```bash
python export_prisma_seed.py
```

This creates `exports/prisma_seed_content.json`, with an array for each Prisma content model, deterministic 24-character IDs, relation IDs, and aggregate counts. It contains:

- 1 Scripture; 18 chapters; 18 chapter modules; 72 chapter-stage lessons and quizzes.
- The 10 thematic sections are also represented as modules, with one lesson and quiz per section. Each theme module is anchored to its first chapter because the requirement's `Module` has one `chapterId`; its lesson links to every verse in its cross-chapter ranges through `LessonVerse`.
- 701 verses, verse translations, and 12,681 word rows. English `translation_en` maps to `VerseTranslation` type `CONTEMPORARY`; `meaning_en` maps to `PRACTICAL`; Hindi verse translations are also `CONTEMPORARY`; word glosses map to `VerseWord`. Chapter names and summaries are retained in English, Hindi, and Sanskrit `ChapterTranslation` rows when present.
- The 9,119 per-verse questions are grouped into four chapter-stage quizzes. The 30 thematic questions are in the thematic lesson quizzes.
- Quiz options are separate `QuizOption` rows. Original type, answer, hint, Sanskrit prompt, verse reference, and other question-specific fields are preserved in `QuizQuestion.metadata` where the app schema has no dedicated field.

The supplied model has no dedicated thematic-section model, so themes use `Module`/`Lesson` and their verse links. `thematic_curriculum` is also retained intact in the seed JSON for clients that need its original section shape and objectives.

To avoid dropping source metadata omitted from the base models, the seed also carries `versesCount` on chapters and optional `speaker`/`commentarySummary` on verses. Add these as optional Prisma fields if typed Prisma access is needed; they remain available in the MongoDB documents regardless.

Do not seed `User`, `UserPreferences`, `LessonProgress`, `QuizAttempt`, `QuizAnswer`, `XPTransaction`, `UserStreak`, or `UserAchievement` from this corpus. Those records belong to Firebase-authenticated users and must be created at runtime. `Achievement` definitions are app policy and are likewise not scripture content.

The requirement attachment is a model specification, not a complete Prisma schema file: it does not define `generator`/`datasource`, and its `ObjectId` scalar needs to match the app's selected Prisma provider. Configure that in the application repository before running Prisma generate/migrate/seed. The JSON seed uses string IDs compatible with the specified ObjectId-shaped IDs and carries the relation fields expected by the models.

## HTTP API

The FastAPI service (`api.py`) exposes:

| Method / path | Response |
|---|---|
| `GET /api/stats` | Counts for chapters, verses, questions, vocabulary. |
| `GET /api/chapters` | Ordered chapter records. |
| `GET /api/curriculum` | Full thematic curriculum including questions. |
| `GET /api/sections` | Ordered section metadata. |
| `GET /api/sections/{section_id}` | One section with its questions; 404 for an unknown ID. |
| `GET /api/chapters/{chapter_number}/verses` | Verse summaries for a chapter, including `meaning_en` and `meaning`. |
| `GET /api/verses/{verse_key}` | Verse record plus `meaning` alias and `vocabulary`. |
| `GET /api/verses/{verse_key}/quiz?level=1` | Verse-level questions; optional `level` filters 1–4. |
| `POST /api/quiz/validate` | Checks `{ "question_id": 123, "user_answer": ... }`, returns correctness, correct answer, explanation, and XP. |

Interactive API docs are at `/docs` when the local FastAPI server is running.

## Integration notes

1. Treat IDs and `verse_key` as opaque identifiers. Sort chapters/verses/questions by their explicit numeric order fields.
2. Render `meaning_en` as the short learning explanation and `translation_en` as the verse translation; expose attribution from `translation_source`.
3. Support Unicode Sanskrit (UTF-8) end-to-end and a sensible font fallback.
4. Decode JSON fields only when loading SQLite directly. In JSON exports, API responses, and MongoDB documents, `options` and `correct_answer` are already decoded.
5. Keep curriculum section questions separate from verse-level questions; they have distinct IDs and schemas.
6. Read `schema.py` for the exact SQLite DDL and `upload_to_mongodb.py` for the canonical MongoDB mapping.
