# Hugging Face dataset assessment for the question bank

Reviewed 2026-10-30. These are source evaluations, not imports. Neither dataset
has been copied into the production question bank.

## JDhruv14/Bhagavad-Gita-QA

Dataset card: <https://huggingface.co/datasets/JDhruv14/Bhagavad-Gita-QA>

- The English subset is listed as about 3,500 rows with `chapter_no`,
  `verse_no`, `question`, and `answer`. The card reports English, Hindi, and
  Gujarati subsets and 10,500 rows total.
- The card says the questions were synthetically generated with GPT-4.1 and
  manually reviewed. It declares MIT. Individual Q&A rows do not include a
  translation source, commentary citation, concept, skill, prerequisite, or
  confidence/review record.
- Its question styles can inspire literal-recall and context prompts. The
  answers are free text, so they cannot be used directly as four-choice answer
  keys without editorial conversion.
- Sample review found interpretive assertions mixed into factual answers. For
  BG1.1, the sample assigns symbolic meaning to Dhritarashtra's blindness;
  BG1.2's sample describes Duryodhana as a cautious strategist who respects
  wisdom. These claims go beyond the verse wording and need a cited commentary
  before use. The sample also describes *maharathi* as a great charioteer,
  which is a suspect gloss in context.
- Recommendation: use it as a **question-idea source only**. Join by chapter and
  verse, check every proposed answer against Sanskrit and a declared translation,
  and rewrite accepted material as original app content with source/editor
  metadata. Do not treat its “manually reviewed” card statement as a substitute
  for our own review.

## Voider22/bhagavad-gita-verses-sanskrit-translations

Dataset card: <https://huggingface.co/datasets/Voider22/bhagavad-gita-verses-sanskrit-translations>

- The viewer lists 701 rows, with verse ID, chapter, verse, Sanskrit `slok`,
  IAST `transliteration`, and named translation/commentary objects including
  Purohit Swami and Sivananda.
- This structure is useful for checking verse IDs, Sanskrit text, IAST, and
  translator-specific English. It is a better match for the source/provenance
  side of our schema than for question writing.
- The card describes it as a direct export from the Vedic Scriptures API and
  declares MIT, with an attribution request. That declaration should not be
  assumed to clear every embedded translation/commentary: each named work may
  have separate rights. Preserve the API attribution and only redistribute
  translations after checking their source terms.
- Recommendation: use it for **cross-checking** Sanskrit/IAST and locating
  translation variants. Do not import every commentary field into our app.
  Adopt one approved translation base for the course and store its author/source
  per verse; keep other traditions as cited editorial references only.

## Fit to our v2 schema

| Need | QA dataset | Sanskrit/translations dataset |
| --- | --- | --- |
| Verse-aligned question ideas | Yes, but quality varies | No |
| Sanskrit and IAST | No | Yes |
| Multiple-choice distractors | No, free-text answers | No |
| Concept/skill/prerequisite tags | No | No |
| Explanation provenance | Not per row | Translator names are present |
| Main use | Inspiration after review | Source-text and translation cross-check |

## Proposed workflow

1. Import neither dataset wholesale.
2. Use the verse dataset to cross-check our chosen source text and transliteration.
3. For each selected verse, consider QA prompts as candidate ideas; reject
   unsupported commentary and rewrite approved questions in our own words.
4. Write each question's correct answer, plausible verse-specific distractors,
   explanation, concept, skill, prerequisite, and source explicitly.
5. Run the v2 validator, then do human doctrinal and pedagogy review.

### Observed Hugging Face metadata

- QA set: 3,500 English rows; 10,500 rows across three languages; row fields
  `chapter_no`, `verse_no`, `question`, `answer`; card declares MIT and notes
  GPT-4.1 generation plus manual review.
- Verse set: 701 rows; includes `slok`, `transliteration`, and named
  translation/commentary fields; card declares MIT for the API export and asks
  for Vedic Scriptures attribution.
