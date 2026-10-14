"""Convert between common Gita IAST-style romanization and Devanagari."""

import re


DEVANAGARI_RE = re.compile(r"[\u0900-\u097f]")

VOWELS = {
    "a": ("अ", ""), "ā": ("आ", "ा"), "i": ("इ", "ि"),
    "ī": ("ई", "ी"), "u": ("उ", "ु"), "ū": ("ऊ", "ू"),
    "ṛ": ("ऋ", "ृ"), "ṝ": ("ॠ", "ॄ"), "ḷ": ("ऌ", "ॢ"),
    "ḹ": ("ॡ", "ॣ"), "e": ("ए", "े"), "ai": ("ऐ", "ै"),
    "o": ("ओ", "ो"), "au": ("औ", "ौ"),
}
CONSONANTS = {
    "kh": "ख", "gh": "घ", "ṅ": "ङ", "chh": "छ", "ch": "च",
    "jh": "झ", "ñ": "ञ", "ṭh": "ठ", "ḍh": "ढ", "ṇ": "ण",
    "th": "थ", "dh": "ध", "ph": "फ", "bh": "भ", "sh": "श",
    "ś": "श", "ṣ": "ष", "ṭ": "ट", "ḍ": "ड", "k": "क",
    "g": "ग", "c": "च", "j": "ज", "t": "त", "d": "द",
    "n": "न", "p": "प", "b": "ब", "m": "म", "y": "य",
    "r": "र", "l": "ल", "v": "व", "w": "व", "ś": "श",
    "ṣ": "ष", "s": "स", "h": "ह",
}
MARKS = {"ṃ": "ं", "ṁ": "ं", "ḥ": "ः", "m̐": "ँ"}
INDEPENDENT_VOWELS = {value[0]: key for key, value in VOWELS.items()}
MATRA_VOWELS = {value[1]: key for key, value in VOWELS.items() if value[1]}
DEVANAGARI_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ṅ",
    "च": "c", "छ": "ch", "ज": "j", "झ": "jh", "ञ": "ñ",
    "ट": "ṭ", "ठ": "ṭh", "ड": "ḍ", "ढ": "ḍh", "ण": "ṇ",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "ś",
    "ष": "ṣ", "स": "s", "ह": "h",
}
DEVANAGARI_MARKS = {value: key for key, value in MARKS.items()}
DEVANAGARI_MARKS["ँ"] = "m̐"


def _normalize_source_roman(text):
    """Normalize the source API's sh and vocalic-r spellings to IAST letters."""
    value = (text or "").strip().lower()
    value = value.replace("ṝi", "ṝ").replace("ṛi", "ṛ")
    value = value.replace("śh", "ś").replace("ṣh", "ṣ")
    return value


def roman_to_devanagari(text):
    """Transliterate Sanskrit romanization to Devanagari, preserving separators."""
    value = _normalize_source_roman(text)
    tokens = sorted(set(VOWELS) | set(CONSONANTS) | set(MARKS), key=len, reverse=True)
    output = []
    i = 0
    while i < len(value):
        match = next((token for token in tokens if value.startswith(token, i)), None)
        if match in VOWELS:
            output.append(VOWELS[match][0])
            i += len(match)
        elif match in CONSONANTS:
            output.append(CONSONANTS[match])
            i += len(match)
            vowel = next((token for token in sorted(VOWELS, key=len, reverse=True)
                          if value.startswith(token, i)), None)
            if vowel:
                output.append(VOWELS[vowel][1])
                i += len(vowel)
            else:
                output.append("्")
        elif match in MARKS:
            output.append(MARKS[match])
            i += len(match)
        else:
            # Hyphens in source compounds are editorial, not Sanskrit letters.
            if value[i] not in "-‐‑–—":
                output.append(value[i])
            i += 1
    return "".join(output)


def devanagari_to_roman(text):
    """Return an IAST transliteration for a Devanagari Sanskrit string."""
    output = []
    value = text or ""
    i = 0
    while i < len(value):
        char = value[i]
        if char in DEVANAGARI_CONSONANTS:
            output.append(DEVANAGARI_CONSONANTS[char])
            i += 1
            if i < len(value) and value[i] in MATRA_VOWELS:
                output.append(MATRA_VOWELS[value[i]])
                i += 1
            elif i < len(value) and value[i] == "्":
                i += 1
            else:
                output.append("a")
        elif char in INDEPENDENT_VOWELS:
            output.append(INDEPENDENT_VOWELS[char])
            i += 1
        elif char in DEVANAGARI_MARKS:
            output.append(DEVANAGARI_MARKS[char])
            i += 1
        else:
            output.append(char)
            i += 1
    return "".join(output)


def normalize_sanskrit_word(value):
    """Return (Devanagari Sanskrit, Roman transliteration) for a source token."""
    word = (value or "").strip()
    if not word:
        return "", ""
    if DEVANAGARI_RE.search(word):
        return word, devanagari_to_roman(word)
    # The source API misspells this frequent name with śh; Sanskrit uses ṣṭ.
    source = word.lower().replace("dhṛitarāśhtr", "dhṛitarāṣhṭr")
    normalized = _normalize_source_roman(source)
    return roman_to_devanagari(normalized), normalized
