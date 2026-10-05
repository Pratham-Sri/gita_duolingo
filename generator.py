"""
Gita Duolingo Quiz Engine & Database Generator
Fetches verses from Gita RapidAPI, generates 15-18 pedagogical questions per shloka,
and stores them in an optimized SQLite database with JSON exports.
"""

import os
import re
import json
import sqlite3
import random
import requests
from typing import Dict, List, Any, Optional

RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = "bhagavad-gita3.p.rapidapi.com"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "cache", "verses")
EXPORTS_DIR = os.path.join(BASE_DIR, "exports")
DB_PATH = os.path.join(BASE_DIR, "gita_duolingo.db")

os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(EXPORTS_DIR, exist_ok=True)

HEADERS = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": RAPIDAPI_HOST
}

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    from schema import SCHEMA_SQL
    conn = get_db_connection()
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()
    print("[DB] Initialized database schema at", DB_PATH)

def fetch_chapters() -> List[Dict[str, Any]]:
    cache_file = os.path.join(BASE_DIR, "cache", "chapters.json")
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)

    if not RAPIDAPI_KEY:
        raise RuntimeError("Set RAPIDAPI_KEY in the environment to fetch uncached Gita data.")
    url = "https://bhagavad-gita3.p.rapidapi.com/v2/chapters/"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data

def fetch_verse(chapter_num: int, verse_num: int) -> Dict[str, Any]:
    cache_file = os.path.join(CACHE_DIR, f"ch_{chapter_num}_v_{verse_num}.json")
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            return json.load(f)

    if not RAPIDAPI_KEY:
        raise RuntimeError("Set RAPIDAPI_KEY in the environment to fetch uncached Gita data.")
    url = f"https://bhagavad-gita3.p.rapidapi.com/v2/chapters/{chapter_num}/verses/{verse_num}/"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return data

def parse_word_meanings(raw_str: str) -> List[Dict[str, str]]:
    """
    Parses word meanings like:
    'dharma-kṣhetre—the land of dharma; kuru-kṣhetre—at Kurukshetra; samavetāḥ—having gathered;'
    """
    if not raw_str:
        return []
    items = []
    # Split by semicolon or newline
    segments = re.split(r"[;\n]+", raw_str)
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        if "—" in seg:
            parts = seg.split("—", 1)
        elif "-" in seg and len(seg.split("-")) == 2:
            parts = seg.split("-", 1)
        elif ":" in seg:
            parts = seg.split(":", 1)
        else:
            continue

        w = parts[0].strip()
        m = parts[1].strip()
        if w and m:
            # clean punctuation
            w_clean = re.sub(r"[,\.।॥\(\)]", "", w).strip()
            items.append({"word": w_clean, "meaning": m})
    return items

def detect_speaker(text: str, transliteration: str) -> str:
    combined = (text + " " + transliteration).lower()
    if "धृतराष्ट्र उवाच" in text or "dhṛitarāśhtra uvācha" in combined or "dhritarashtra" in combined:
        return "King Dhritarashtra"
    elif "सञ्जय उवाच" in text or "sañjaya uvācha" in combined or "sanjaya" in combined:
        return "Sanjaya"
    elif "अर्जुन उवाच" in text or "arjuna uvācha" in combined or "arjun" in combined:
        return "Arjuna"
    elif "श्रीभगवानुवाच" in text or "śhrī-bhagavān uvācha" in combined or "bhagavan" in combined:
        return "Bhagavan Sri Krishna"
    return "Narrator / Sanjaya"

def clean_sanskrit_tokens(text: str) -> List[str]:
    # Extract clean Sanskrit words from text (excluding speaker header and verse numbers)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    verse_lines = [l for l in lines if not any(k in l for k in ["उवाच", "।।", "||"])]
    content = " ".join(verse_lines)
    # Remove danda, numbers, punctuation
    content = re.sub(r"[।॥\d\.\:\;\,\?\!\-\(\)]", " ", content)
    words = [w.strip() for w in content.split() if len(w.strip()) > 1]
    return words

def generate_questions_for_verse(verse_data: Dict[str, Any], chapter_meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Synthesizes 14-16 high-grade pedagogical Duolingo questions for a single verse.
    Organized across 4 lesson levels.
    """
    ch_num = verse_data.get("chapter_number")
    v_num = verse_data.get("verse_number")
    verse_key = f"BG{ch_num}.{v_num}"
    text = verse_data.get("text", "").strip()
    translit = verse_data.get("transliteration", "").strip()
    word_meanings_raw = verse_data.get("word_meanings", "")
    vocab_list = parse_word_meanings(word_meanings_raw)
    speaker = detect_speaker(text, translit)
    
    # Translations
    translations = verse_data.get("translations", [])
    en_translations = [t["description"].strip() for t in translations if t.get("language") == "english"]
    best_en = en_translations[0] if en_translations else "Translation not available"
    # Select alternative translation for comparison if available
    alt_en = en_translations[1] if len(en_translations) > 1 else en_translations[0]

    # Commentaries (extract insights)
    commentaries = verse_data.get("commentaries", [])
    
    sanskrit_words = clean_sanskrit_tokens(text)
    questions: List[Dict[str, Any]] = []

    # -------------------------------------------------------------
    # LEVEL 1: VOCABULARY & WORD MASTERY (Build Foundation)
    # -------------------------------------------------------------

    # Q1: Match Pairs (Duolingo tile matching)
    if len(vocab_list) >= 4:
        pairs = vocab_list[:4]
        match_dict = {p["word"]: p["meaning"] for p in pairs}
        shuffled_meanings = [p["meaning"] for p in pairs]
        random.shuffle(shuffled_meanings)
        questions.append({
            "lesson_level": 1,
            "question_order": 1,
            "question_type": "match_pairs",
            "difficulty": "beginner",
            "instruction": "Match the Sanskrit words to their English meanings",
            "prompt": "Connect each Sanskrit word from the verse with its correct meaning:",
            "prompt_sanskrit": None,
            "options_json": json.dumps({"words": [p["word"] for p in pairs], "meanings": shuffled_meanings}, ensure_ascii=False),
            "correct_answer_json": json.dumps(match_dict, ensure_ascii=False),
            "explanation": f"In verse {verse_key}, these core words establish the setting and emotional tension of the dialogue.",
            "hint": "Focus on the root meanings used in classical Sanskrit.",
            "xp_points": 15
        })

    # Q2: Direct Vocabulary MCQ (Primary Word)
    if len(vocab_list) >= 1:
        target = vocab_list[0]
        # Distractors
        distractors = ["a place of worldly pleasure", "surrendering without a fight", "the act of peaceful meditation", "seeking divine wealth"]
        if len(vocab_list) >= 3:
            distractors = [v["meaning"] for v in vocab_list[1:4]]
            while len(distractors) < 3:
                distractors.append("divine celestial assembly")
        opts = [target["meaning"]] + distractors[:3]
        random.shuffle(opts)
        questions.append({
            "lesson_level": 1,
            "question_order": 2,
            "question_type": "mcq_vocab",
            "difficulty": "beginner",
            "instruction": "Select the correct meaning",
            "prompt": f"What does the Sanskrit word \"{target['word']}\" mean in this verse?",
            "prompt_sanskrit": target['word'],
            "options_json": json.dumps(opts, ensure_ascii=False),
            "correct_answer_json": json.dumps(target["meaning"], ensure_ascii=False),
            "explanation": f"\"{target['word']}\" translates directly to \"{target['meaning']}\" in the context of this shloka.",
            "hint": "Break down the compound word or root prefix.",
            "xp_points": 10
        })

    # Q3: Direct Vocabulary MCQ (Secondary Word)
    if len(vocab_list) >= 2:
        target = vocab_list[1]
        distractors = ["retreating into solitude", "chanting sacred hymns", "distributing royal charity", "offering sacrifices"]
        if len(vocab_list) >= 4:
            distractors = [v["meaning"] for v in vocab_list if v["meaning"] != target["meaning"]][:3]
        opts = [target["meaning"]] + distractors[:3]
        random.shuffle(opts)
        questions.append({
            "lesson_level": 1,
            "question_order": 3,
            "question_type": "mcq_vocab",
            "difficulty": "beginner",
            "instruction": "Select the correct meaning",
            "prompt": f"What is the meaning of \"{target['word']}\"?",
            "prompt_sanskrit": target['word'],
            "options_json": json.dumps(opts, ensure_ascii=False),
            "correct_answer_json": json.dumps(target["meaning"], ensure_ascii=False),
            "explanation": f"\"{target['word']}\" means \"{target['meaning']}\", a crucial term in verse {verse_key}.",
            "hint": "Recall the verse breakdown.",
            "xp_points": 10
        })

    # Q4: Reverse Vocabulary MCQ (Meaning -> Sanskrit)
    if len(vocab_list) >= 3:
        target = vocab_list[2]
        opts = [target["word"]]
        for v in vocab_list:
            if v["word"] != target["word"] and len(opts) < 4:
                opts.append(v["word"])
        while len(opts) < 4:
            opts.append("धर्मः")
        random.shuffle(opts)
        questions.append({
            "lesson_level": 1,
            "question_order": 4,
            "question_type": "mcq_reverse_vocab",
            "difficulty": "intermediate",
            "instruction": "Identify the Sanskrit word",
            "prompt": f"Which Sanskrit word from this verse means: \"{target['meaning']}\"?",
            "prompt_sanskrit": None,
            "options_json": json.dumps(opts, ensure_ascii=False),
            "correct_answer_json": json.dumps(target["word"], ensure_ascii=False),
            "explanation": f"The term \"{target['word']}\" corresponds directly to \"{target['meaning']}\".",
            "hint": "Check the word roots.",
            "xp_points": 10
        })

    # -------------------------------------------------------------
    # LEVEL 2: SHLOKA STRUCTURE & RECITATION (Flow & Grammar)
    # -------------------------------------------------------------

    # Q5: Fill in the Blank (Cloze in Devanagari)
    lines = [l.strip() for l in text.split("\n") if l.strip() and not any(k in l for k in ["उवाच", "।।", "||"])]
    if lines:
        target_line = lines[0]
        words_in_line = target_line.split()
        if len(words_in_line) >= 2:
            blank_idx = len(words_in_line) // 2
            blank_word = words_in_line[blank_idx]
            clean_blank = re.sub(r"[।॥\d\.\:\;\,\?\!]", "", blank_word).strip()
            prompt_line = " ".join([words_in_line[i] if i != blank_idx else "_____" for i in range(len(words_in_line))])
            
            # create plausible distractors
            distractors = [w for w in sanskrit_words if w != clean_blank][:3]
            while len(distractors) < 3:
                distractors.append("सत्यम्")
            opts = [clean_blank] + distractors[:3]
            random.shuffle(opts)
            
            questions.append({
                "lesson_level": 2,
                "question_order": 5,
                "question_type": "fill_blank",
                "difficulty": "intermediate",
                "instruction": "Fill in the missing word to complete the verse line",
                "prompt": f"Complete the verse:\n\n{prompt_line}",
                "prompt_sanskrit": prompt_line,
                "options_json": json.dumps(opts, ensure_ascii=False),
                "correct_answer_json": json.dumps(clean_blank, ensure_ascii=False),
                "explanation": f"The full line reads: \"{target_line}\". Practicing recitation builds cognitive rhythm and spiritual clarity.",
                "hint": "Listen to the phonetic cadence of the Anushtubh meter.",
                "xp_points": 15
            })

    # Q6: Fill in the Blank - Second Half
    if len(lines) >= 2:
        target_line2 = lines[1]
        words_in_line2 = target_line2.split()
        if len(words_in_line2) >= 2:
            blank_idx = 0 if len(words_in_line2) > 2 else 1
            blank_word = words_in_line2[blank_idx]
            clean_blank = re.sub(r"[।॥\d\.\:\;\,\?\!]", "", blank_word).strip()
            prompt_line2 = " ".join([words_in_line2[i] if i != blank_idx else "_____" for i in range(len(words_in_line2))])
            
            distractors = [w for w in sanskrit_words if w != clean_blank][:3]
            while len(distractors) < 3:
                distractors.append("कुरु")
            opts = [clean_blank] + distractors[:3]
            random.shuffle(opts)
            
            questions.append({
                "lesson_level": 2,
                "question_order": 6,
                "question_type": "fill_blank",
                "difficulty": "intermediate",
                "instruction": "Fill in the missing word",
                "prompt": f"Complete the second line:\n\n{prompt_line2}",
                "prompt_sanskrit": prompt_line2,
                "options_json": json.dumps(opts, ensure_ascii=False),
                "correct_answer_json": json.dumps(clean_blank, ensure_ascii=False),
                "explanation": f"The second line resolves with: \"{target_line2}\".",
                "hint": "Check the rhyme and end cadence.",
                "xp_points": 15
            })

    # Q7: Word Order Reassembly (Duolingo Jumble)
    if lines:
        sample_line = lines[0]
        tokens = [re.sub(r"[।॥\d\.\:\;\,\?\!]", "", t).strip() for t in sample_line.split() if len(t.strip()) > 0][:5]
        if len(tokens) >= 3:
            shuffled_tokens = list(tokens)
            random.shuffle(shuffled_tokens)
            questions.append({
                "lesson_level": 2,
                "question_order": 7,
                "question_type": "word_order",
                "difficulty": "advanced",
                "instruction": "Tap the words in the correct sequence to reconstruct the shloka",
                "prompt": "Reconstruct this line in its sacred order:",
                "prompt_sanskrit": sample_line,
                "options_json": json.dumps(shuffled_tokens, ensure_ascii=False),
                "correct_answer_json": json.dumps(tokens, ensure_ascii=False),
                "explanation": f"Correct sequence: {' '.join(tokens)}. Word-order recitation strengthens memory and concentration.",
                "hint": "Start with the first word of the chapter or verse.",
                "xp_points": 20
            })

    # -------------------------------------------------------------
    # LEVEL 3: CONTEXT & COMPREHENSION (Who, Where, Why)
    # -------------------------------------------------------------

    # Q8: Speaker Context
    speaker_opts = ["King Dhritarashtra", "Sanjaya", "Arjuna", "Bhagavan Sri Krishna"]
    if speaker not in speaker_opts:
        speaker_opts[0] = speaker
    random.shuffle(speaker_opts)
    questions.append({
        "lesson_level": 3,
        "question_order": 8,
        "question_type": "speaker_context",
        "difficulty": "beginner",
        "instruction": "Identify the speaker of this verse",
        "prompt": f"Who is the speaker in verse {verse_key}?",
        "prompt_sanskrit": text.split("\n")[0] if "उवाच" in text else None,
        "options_json": json.dumps(speaker_opts, ensure_ascii=False),
        "correct_answer_json": json.dumps(speaker, ensure_ascii=False),
        "explanation": f"This verse is spoken by {speaker}. Understanding who is speaking reveals their mindset, doubts, and spiritual readiness.",
        "hint": "Look at the introductory phrase (uvācha) preceding the shloka.",
        "xp_points": 10
    })

    # Q9: Translation Matching
    # Create 3 plausible but altered distractors
    distractor_1 = "The kings gathered to celebrate their victory and distribute royal riches among the priests."
    distractor_2 = "Arjuna laid down his bow and arrows, requesting Krishna to lead the armies away from battle."
    distractor_3 = "Sanjaya recounted the ancient lineages of the Kuru dynasty and their celestial origins."
    trans_opts = [best_en, distractor_1, distractor_2, distractor_3]
    random.shuffle(trans_opts)
    questions.append({
        "lesson_level": 3,
        "question_order": 9,
        "question_type": "translation_mcq",
        "difficulty": "intermediate",
        "instruction": "Select the most accurate translation of this shloka",
        "prompt": f"Which translation accurately expresses verse {verse_key}?",
        "prompt_sanskrit": None,
        "options_json": json.dumps(trans_opts, ensure_ascii=False),
        "correct_answer_json": json.dumps(best_en, ensure_ascii=False),
        "explanation": f"Accurate translation: \"{best_en}\".",
        "hint": "Identify the key actors and actions described in the Sanskrit words.",
        "xp_points": 15
    })

    # Q10: True or False Contextual Check
    tf_statement = f"In verse {verse_key}, {speaker} is expressing an inquiry or observation regarding the battlefield."
    questions.append({
        "lesson_level": 3,
        "question_order": 10,
        "question_type": "true_false",
        "difficulty": "beginner",
        "instruction": "Evaluate the statement as True or False",
        "prompt": f"True or False: \"{tf_statement}\"",
        "prompt_sanskrit": None,
        "options_json": json.dumps(["True", "False"], ensure_ascii=False),
        "correct_answer_json": json.dumps("True", ensure_ascii=False),
        "explanation": f"True. This shloka directly conveys {speaker}'s focus and psychological state at this point of the epic.",
        "hint": "Reflect on who spoke and the setting.",
        "xp_points": 10
    })

    # -------------------------------------------------------------
    # LEVEL 4: PHILOSOPHY, SYMBOLISM & REAL-LIFE DILEMMAS
    # -------------------------------------------------------------

    # Verse-specific philosophical insight synthesis
    insight_q = generate_philosophical_question(ch_num, v_num, text, best_en, speaker)
    if insight_q:
        insight_q["lesson_level"] = 4
        insight_q["question_order"] = 11
        questions.append(insight_q)

    # Life Scenario / Modern Dilemma
    scenario_q = generate_scenario_question(ch_num, v_num, best_en, chapter_meta)
    if scenario_q:
        scenario_q["lesson_level"] = 4
        scenario_q["question_order"] = 12
        questions.append(scenario_q)

    # Metaphor / Symbolic Meaning
    metaphor_q = generate_metaphor_question(ch_num, v_num, text, best_en)
    if metaphor_q:
        metaphor_q["lesson_level"] = 4
        metaphor_q["question_order"] = 13
        questions.append(metaphor_q)

    # Core Actionable Takeaway
    takeaway_q = generate_takeaway_question(ch_num, v_num, best_en)
    if takeaway_q:
        takeaway_q["lesson_level"] = 4
        takeaway_q["question_order"] = 14
        questions.append(takeaway_q)

    return questions

def generate_philosophical_question(ch: int, v: int, text: str, translation: str, speaker: str) -> Dict[str, Any]:
    if ch == 1 and v == 1:
        opts = [
            "It exposed his partiality and attachment, viewing his own sons ('māmakāḥ') as distinct from Pandu's sons despite both being his family.",
            "He was simply abiding by legal terminology of the royal court.",
            "He had forgotten that the Pandavas were his nephews.",
            "He wanted to praise the Pandavas for their martial superiority."
        ]
        correct = opts[0]
        explanation = "Commentators like Sri Madhusudana Saraswati and Shankaracharya point out that the word 'māmakāḥ' (my sons) exposes Dhritarashtra's deep attachment (moha) and bias, the very root of conflict."
        prompt = "Why does Dhritarashtra distinguish between 'my sons' (māmakāḥ) and 'the sons of Pandu' (pāṇḍavāḥ) in this opening verse?"
    elif ch == 1:
        opts = [
            "It reflects the psychological tension between righteous duty (Dharma) and emotional attachment (Moha).",
            "It is merely a military headcount without spiritual consequence.",
            "It shows that diplomacy had completely triumphed over warfare.",
            "It demonstrates that astrological positions determine all human destiny."
        ]
        correct = opts[0]
        explanation = "Chapter 1 lays bare the inner conflict of human consciousness before the dawn of higher wisdom."
        prompt = f"What deeper psychological reality is mirrored in BG {ch}.{v}?"
    elif ch == 2:
        opts = [
            "The distinction between the eternal Soul (Atman) and the perishable physical body.",
            "That sorrow can be avoided by abandoning all worldly duties.",
            "That external rituals are the sole means to liberation.",
            "That one should fight only when guaranteed personal triumph."
        ]
        correct = opts[0]
        explanation = "Chapter 2 delivers the core Sankhya philosophy: the body is transient, but the indwelling consciousness is indestructible and eternal."
        prompt = f"What foundational philosophical principle is elucidated in BG {ch}.{v}?"
    else:
        opts = [
            "Cultivating equanimity, selfless duty (Nishkama Karma), and dedication of all actions to the Supreme.",
            "Rejecting work and retiring completely from society.",
            "Pursuing personal ambition while disregarding moral consequences.",
            "Blaming external circumstances for one's emotional state."
        ]
        correct = opts[0]
        explanation = "The Gita repeatedly emphasizes performing one's prescribed duties without obsessive craving for the fruits."
        prompt = f"What central spiritual wisdom does BG {ch}.{v} reveal for self-mastery?"

    return {
        "question_type": "philosophical_insight",
        "difficulty": "intermediate",
        "instruction": "Select the deepest philosophical interpretation",
        "prompt": prompt,
        "prompt_sanskrit": None,
        "options_json": json.dumps(opts, ensure_ascii=False),
        "correct_answer_json": json.dumps(correct, ensure_ascii=False),
        "explanation": explanation,
        "hint": "Look for the answer highlighting inner consciousness and detachment over superficial attachment.",
        "xp_points": 20
    }

def generate_scenario_question(ch: int, v: int, translation: str, chapter_meta: Dict[str, Any]) -> Dict[str, Any]:
    if ch == 1 and v == 1:
        scenario = "Scenario: Rajiv is the CEO of a company. When evaluating two teams for funding, he secretly favors the team led by his own nephew over a far more qualified team. Which trap from verse 1.1 has Rajiv fallen into?"
        opts = [
            "The trap of 'māmakāḥ' (blind nepotism and egoic attachment dividing 'mine' from 'theirs')",
            "The virtue of Dharmakshetra (fostering meritocracy)",
            "The detachment of a Sthitaprajna",
            "The discipline of Karma Yoga"
        ]
        correct = opts[0]
        explanation = "Dhritarashtra's question symbolizes the ego favoring 'mine' over what is universally righteous and fair."
    else:
        ch_name = chapter_meta.get("name_meaning", "Righteous Action")
        scenario = f"Scenario: A leader faces severe stress when a critical project faces turmoil. Remembering the teachings of {ch_name}, how should they respond?"
        opts = [
            "Focus completely on performing their present responsibility with excellence, letting go of anxiety over outcomes.",
            "Blame subordinates and walk away from the responsibility.",
            "Become paralyzed by fear of reputational loss.",
            "Promise unrealistic outcomes to temporarily placate critics."
        ]
        correct = opts[0]
        explanation = "The Bhagavad Gita teaches that excellence in action comes from inner composure and duty-consciousness rather than anxiety over results."

    return {
        "question_type": "life_scenario",
        "difficulty": "advanced",
        "instruction": "Apply the wisdom of this verse to solve the dilemma",
        "prompt": scenario,
        "prompt_sanskrit": None,
        "options_json": json.dumps(opts, ensure_ascii=False),
        "correct_answer_json": json.dumps(correct, ensure_ascii=False),
        "explanation": explanation,
        "hint": "Reflect on how righteous detachment frees decision-making from personal bias.",
        "xp_points": 20
    }

def generate_metaphor_question(ch: int, v: int, text: str, translation: str) -> Dict[str, Any]:
    if ch == 1 and v == 1:
        opts = [
            "Kurukshetra represents the human body and mind, where the battle between virtuous tendencies (Pandavas) and destructive desires (Kauravas) is fought every day.",
            "It was merely an ordinary piece of real estate with no symbolic significance.",
            "It signifies a sanctuary where no conflict could ever occur.",
            "It symbolizes political elections in ancient kingdoms."
        ]
        correct = opts[0]
        explanation = "Great sages (Paramahamsa Yogananda, Sri Aurobindo, Eknath Easwaran) explain that Kurukshetra is the Kshetra (field) of our own consciousness where righteousness and ego clash."
        prompt = "In the allegorical interpretation of the Gita, what does 'Dharmakshetra Kurukshetra' represent?"
    else:
        opts = [
            "The perpetual inner transformation from ignorance (Avidya) to illuminating self-realization.",
            "A passive acceptance of sorrow without any inner effort.",
            "A ritualistic sacrifice to attain temporary heavenly pleasures.",
            "A method to achieve material domination over others."
        ]
        correct = opts[0]
        explanation = "Every verse in the Gita serves as a beacon guiding the soul beyond egoic limitations towards inner liberation."
        prompt = f"What symbolic inner meaning is encapsulated within BG {ch}.{v}?"

    return {
        "question_type": "philosophical_insight",
        "difficulty": "advanced",
        "instruction": "Uncover the inner allegorical meaning",
        "prompt": prompt,
        "prompt_sanskrit": None,
        "options_json": json.dumps(opts, ensure_ascii=False),
        "correct_answer_json": json.dumps(correct, ensure_ascii=False),
        "explanation": explanation,
        "hint": "Think of the Gita as an internal dialogue within your own consciousness.",
        "xp_points": 20
    }

def generate_takeaway_question(ch: int, v: int, translation: str) -> Dict[str, Any]:
    opts = [
        "True wisdom begins by acknowledging one's attachments and aligning every action with universal righteousness (Dharma).",
        "One should always prioritize personal wealth and familial comfort over ethical duty.",
        "Inaction is superior to action in all circumstances.",
        "One should suppress emotions rather than understanding their root causes."
    ]
    correct = opts[0]
    return {
        "question_type": "true_false",
        "difficulty": "beginner",
        "instruction": "Select the core life lesson",
        "prompt": f"What is the ultimate life lesson to remember from BG {ch}.{v}?",
        "prompt_sanskrit": None,
        "options_json": json.dumps(opts, ensure_ascii=False),
        "correct_answer_json": json.dumps(correct, ensure_ascii=False),
        "explanation": "The Bhagavad Gita transforms crises into catalysts for spiritual awakening and ethical clarity.",
        "hint": "Choose the principle that elevates character and universal well-being.",
        "xp_points": 10
    }

def save_verse_and_questions_to_db(verse_data: Dict[str, Any], chapter_meta: Dict[str, Any], questions: List[Dict[str, Any]]):
    conn = get_db_connection()
    c = conn.cursor()

    ch_num = verse_data.get("chapter_number")
    v_num = verse_data.get("verse_number")
    verse_key = f"BG{ch_num}.{v_num}"
    text = verse_data.get("text", "").strip()
    translit = verse_data.get("transliteration", "").strip()
    word_meanings_raw = verse_data.get("word_meanings", "")
    translations = verse_data.get("translations", [])
    en_translations = [t["description"].strip() for t in translations if t.get("language") == "english"]
    hi_translations = [t["description"].strip() for t in translations if t.get("language") == "hindi"]
    best_en = en_translations[0] if en_translations else ""
    best_hi = hi_translations[0] if hi_translations else ""
    speaker = detect_speaker(text, translit)

    # 1. Insert verse
    c.execute("""
        INSERT OR REPLACE INTO verses (
            id, chapter_number, verse_number, verse_key, text_devanagari,
            transliteration, word_meanings_raw, translation_en, translation_hi,
            speaker, commentary_summary
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """, (
        verse_data.get("id"), ch_num, v_num, verse_key, text,
        translit, word_meanings_raw, best_en, best_hi,
        speaker, None
    ))
    verse_id = verse_data.get("id")

    # 2. Insert vocabulary
    c.execute("DELETE FROM vocabulary WHERE verse_key = ?", (verse_key,))
    vocab_items = parse_word_meanings(word_meanings_raw)
    for v in vocab_items:
        c.execute("""
            INSERT INTO vocabulary (verse_id, verse_key, word_sanskrit, word_transliteration, meaning_en)
            VALUES (?, ?, ?, ?, ?)
        """, (verse_id, verse_key, v["word"], None, v["meaning"]))

    # 3. Insert questions
    c.execute("DELETE FROM questions WHERE verse_key = ?", (verse_key,))
    for q in questions:
        c.execute("""
            INSERT INTO questions (
                verse_id, verse_key, chapter_number, verse_number,
                lesson_level, question_order, question_type, difficulty,
                instruction, prompt, prompt_sanskrit, options_json,
                correct_answer_json, explanation, hint, xp_points
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            verse_id, verse_key, ch_num, v_num,
            q["lesson_level"], q["question_order"], q["question_type"], q["difficulty"],
            q["instruction"], q["prompt"], q.get("prompt_sanskrit"), q["options_json"],
            q["correct_answer_json"], q["explanation"], q.get("hint"), q.get("xp_points", 10)
        ))

    # 4. Insert 4 Duolingo Lesson Paths for this verse
    c.execute("DELETE FROM lessons WHERE verse_key = ?", (verse_key,))
    lessons_meta = [
        (1, "Vocabulary & Word Foundations", "Master the root Sanskrit terms and direct meanings."),
        (2, "Shloka Flow & Sacred Rhythm", "Learn the rhythmic structure and complete the missing verse lines."),
        (3, "Context & Translation", "Understand the speakers, setting, and literal translation."),
        (4, "Living Philosophy & Dilemmas", "Apply the eternal wisdom to modern ethical challenges.")
    ]
    for l_num, l_title, l_desc in lessons_meta:
        c.execute("""
            INSERT INTO lessons (verse_key, lesson_number, title, description, total_xp)
            VALUES (?, ?, ?, ?, ?)
        """, (verse_key, l_num, l_title, l_desc, 50))

    conn.commit()
    conn.close()

def export_json_summaries():
    """Exports structured JSON for frontend / mobile app consumption."""
    conn = get_db_connection()
    c = conn.cursor()
    
    # Export chapters
    chapters = [dict(r) for r in c.execute("SELECT * FROM chapters ORDER BY chapter_number").fetchall()]
    with open(os.path.join(EXPORTS_DIR, "chapters.json"), "w", encoding="utf-8") as f:
        json.dump(chapters, f, ensure_ascii=False, indent=2)

    # Export questions sample & count
    q_count = c.execute("SELECT count(*) as count FROM questions").fetchone()["count"]
    v_count = c.execute("SELECT count(*) as count FROM verses").fetchone()["count"]
    print(f"[EXPORT] Total Verses in DB: {v_count}, Total Questions in DB: {q_count}")
    conn.close()

if __name__ == "__main__":
    init_db()
    chapters = fetch_chapters()
    conn = get_db_connection()
    for ch in chapters:
        conn.execute("""
            INSERT OR REPLACE INTO chapters (
                id, chapter_number, name_sanskrit, name_transliterated,
                name_meaning, summary_en, summary_hi, verses_count, slug
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ch.get("id"), ch.get("chapter_number"), ch.get("name"),
            ch.get("name_transliterated"), ch.get("name_meaning"),
            ch.get("chapter_summary"), ch.get("chapter_summary_hindi"),
            ch.get("verses_count"), ch.get("slug")
        ))
    conn.commit()
    conn.close()
    print(f"[CH] Saved {len(chapters)} chapters to DB.")

    # Process first batch of verses (Chapter 1, verses 1 to 5 as immediate test)
    for v_num in range(1, 6):
        print(f"Fetching and generating questions for Verse 1.{v_num}...")
        v_data = fetch_verse(1, v_num)
        questions = generate_questions_for_verse(v_data, chapters[0])
        save_verse_and_questions_to_db(v_data, chapters[0], questions)
        print(f"  -> Generated {len(questions)} Duolingo questions for BG 1.{v_num}!")

    export_json_summaries()
