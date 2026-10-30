# Question bank v2 contract

The current 9,119-row bank is legacy content. It must not be treated as a
curated comprehension course: the audit in `exports/question_bank_audit.json`
records the problems found in the live SQLite bank.

## Course shape

- Curate 100–150 core verses for the main learning path.
- Give each core verse 4–6 authored comprehension questions.
- Present narrative-only verses as context cards; do not quiz every verse with
  the same weight.
- Preserve the corpus's 701 source keys, including BG 13.1, and document that
  numbering convention wherever another edition uses 700 verses.
- The current draft selects 122 core verses, adds BG 2.7 and BG 4.6, moves Chapter 1's
  narrative sequence to context cards, tags concepts, and records prerequisites.
- Use Shri Purohit Swami's 1935 translation as the single source base where the
  cached translation is available. Write original plain-English paraphrases;
  keep the base translation and attribution separate. Confirm rights for the
  intended publication jurisdiction before release.
- Each selected verse has five question records: meaning, context, inference,
  application, and vocabulary. The generated full bank has 610 records.
- The English Q&A Hugging Face dataset supplies candidate stems and explanation
  material only. Each record retains its candidate question and remains marked
  `editorial-review-required` until a subject-matter review is complete.

## Question record

Each authored question must contain:

```json
{
  "id": "BG2.47.meaning.01",
  "verse_key": "BG2.47",
  "question_type": "meaning | context | inference | application | vocabulary",
  "skill": "recall | interpretation | inference | transfer",
  "difficulty": "beginner | intermediate | advanced",
  "concept": "karma_yoga",
  "prerequisite_concept": "duty",
  "prerequisite_verse": "BG2.31",
  "source": "JDhruv14/Bhagavad-Gita-QA candidate; verify before use",
  "prompt": "...",
  "options": ["...", "...", "...", "..."],
  "correct_answer": "...",
  "explanation": "Gloss + context + plain-English restatement."
}
```

Distractors must describe plausible misunderstandings of the same teaching.
Do not copy clauses from unrelated verses. `difficulty` is a content-based
provisional estimate and should be recalibrated from learner results. Sanskrit
display text omits verse-number markers; transliteration remains Roman Sanskrit.
Purohit Swami's translation is stored as an attributed reference, not shown as
the learner-facing paraphrase.

## Review gate

Run `python scripts/build_question_bank_v2.py` to regenerate
`data/curated_question_bank.json`, `exports/curated_question_bank_review.csv`,
and the review table `curated_questions_v2` in `database/gita_duolingo.db`.
The builder preserves the legacy table's app fields and adds nullable v2
metadata, then creates `curated_questions_v2` with the same column names and
types. It carries legacy questions into the current table for verses outside
the 122-verse curated set, tagged `legacy-fallback`, so every verse in a
six-verse lesson has questions available. Run
`python scripts/validate_question_bank_v2.py` before migration. Automated
checks cover format, one question of every type per verse, unique stems,
balanced answer positions and option style/length. They do not establish
doctrinal accuracy. Every record remains review-gated until a human verifies
the meaning, distractor plausibility, and source attribution.
