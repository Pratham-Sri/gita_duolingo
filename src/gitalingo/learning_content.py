"""Small, reproducible helpers for tagging and quiz distractors."""

import random
import re
import heapq
from collections import Counter


DEVANAGARI_WORD = re.compile(r"[\u0900-\u097f]+")
PUNCTUATION = re.compile(r"[।॥\d.,:;?!()\[\]{}]+")

PRONOUNS = (
    "he ", "she ", "they ", "we ", "you ", "i ", "it ", "this ", "that ",
    "who ", "whom ", "whose ", "which ", "what ", "my ", "your ", "our ",
    "his ", "her ", "their ", "oneself", "one's ",
)
PARTICLES = {
    "and", "but", "also", "or", "nor", "indeed", "certainly", "only",
    "even", "not", "no", "yes", "thus", "therefore", "then", "now", "here",
    "there", "again", "ever", "always", "just", "surely", "verily", "as",
    "like", "while", "although", "because", "if", "when", "where", "how",
}
SANSKRIT_PARTICLES = {
    "ca", "cha", "eva", "tu", "hi", "api", "na", "atha", "kila", "iva",
    "iti", "kim", "nu", "vai", "sma", "u", "ha", "mā", "ma", "nanu",
}
VERB_PREFIXES = (
    "said", "spoke", "asked", "did ", "does ", "do ", "is ", "are ", "was ",
    "were ", "become", "became", "knows", "know ", "understand", "reached",
    "approached", "went ", "goes ", "moves", "acts ", "act ", "sees ", "saw ",
    "hears", "heard", "speaking", "saying", "to know", "to see", "to do",
    "to act", "to speak", "to hear", "having ", "desiring ", "looking ",
    "seeing ", "hearing ", "standing ", "seated ", "being ", "having been ",
)
FIRST_PERSON_VERB_GLOSSES = (
    "i recount", "i say", "i speak", "i tell", "i know", "i see", "i do",
    "i act", "i teach", "i describe", "i am", "we say", "we speak",
)
NOUN_HEADS = {
    "warrior", "warriors", "conch", "conches", "bow", "bows", "king", "kings",
    "army", "armies", "field", "battlefield", "chariot", "chariots", "man",
    "men", "person", "people", "lord", "teacher", "disciple", "son", "sons",
    "daughter", "daughters", "body", "bodies", "soul", "self", "mind", "minds",
    "action", "actions", "duty", "duties", "knowledge", "wisdom", "word", "words",
    "desire", "desires", "sense", "senses", "quality", "qualities", "virtue",
    "virtues", "kingdom", "kingdoms", "weapon", "weapons", "sound", "sounds",
}
ADJECTIVE_PREFIXES = (
    "great ", "mighty ", "wise ", "powerful ", "righteous ", "divine ",
    "eternal ", "supreme ", "highest ", "best ", "noble ", "strong ",
    "fearless ", "devoted ", "learned ", "ancient ", "many ", "all ",
    "every ", "whole ", "various ", "excellent ", "immortal ", "imperishable ",
)
PROPER_NAMES = {
    "arjuna", "krishna", "bhagavan", "dhritarashtra", "sanjaya", "sanjay",
    "bhima", "bheema", "yudhishthira", "nakula", "sahadeva", "duryodhana",
    "drona", "drupada", "karna", "kunti", "pandu", "vasudeva", "madhusudana",
    "govinda", "kesava", "vasudev", "janardana", "achyuta", "partha", "kaunteya",
    "kurukshetra", "hastinapura", "bharata", "kuru", "pandava", "kaurava",
}


def grammatical_info(word, meaning):
    """Return a broad POS label using the supplied word gloss as context."""
    gloss = re.sub(r"\s+", " ", (meaning or "").strip().lower())
    first = gloss.split("—", 1)[0].strip()
    word_key = re.sub(r"[^a-zāīūṛṝḷḹṃḥṅñṭḍṇśṣ']", "", (word or "").lower())
    if not gloss:
        return "Noun / compound (provisional)"
    if gloss.startswith(FIRST_PERSON_VERB_GLOSSES):
        return "Verb"
    if re.search(r"\b(my|your|his|her|our|their|mine|yours|theirs)\b", gloss):
        return "Pronoun"
    if re.match(r"(?:on|by|after|before|while)\s+\w+ing\b", gloss):
        return "Verb (absolutive / participle)"
    if re.match(r".+\s+(?:said|spoke|asked|recounted|declared)$", gloss) and any(name in gloss for name in PROPER_NAMES):
        return "Proper noun + verb phrase"
    if gloss in {"what", "who", "whom", "whose", "which", "this", "that", "these", "those"}:
        return "Pronoun"
    if word_key in SANSKRIT_PARTICLES:
        return "Conjunction" if word_key in {"ca", "cha"} else "Particle / indeclinable"
    if first in PARTICLES or gloss in PARTICLES:
        if first in {"and", "but", "or", "nor", "although", "because", "if", "when", "while"}:
            return "Conjunction"
        if first in {"here", "there", "then", "now", "again", "always", "ever", "thus", "therefore", "where", "how"}:
            return "Adverb"
        return "Particle / indeclinable"
    if gloss in {"i", "you", "he", "she", "they", "we", "it", "who", "what", "this", "that"} or gloss.startswith(PRONOUNS):
        return "Pronoun"
    if any(name in gloss for name in PROPER_NAMES):
        return "Proper noun"
    if gloss.startswith(VERB_PREFIXES):
        if gloss.startswith(("having ", "desiring ", "looking ", "seeing ", "hearing ", "standing ", "seated ", "being ")):
            return "Participle / verbal adjective"
        return "Verb"
    if gloss.startswith(ADJECTIVE_PREFIXES) and not any(
        re.search(rf"\b{re.escape(head)}\b", gloss) for head in NOUN_HEADS
    ):
        return "Adjective"
    if gloss.startswith(("in ", "at ", "on ", "from ", "by ", "of ", "for ", "with ", "unto ", "among ", "toward ", "into ")):
        return "Noun / compound (oblique case)"
    if gloss.startswith(("one ", "two ", "three ", "four ", "first ", "second ", "many ", "several ")):
        return "Numeral"
    # Most remaining source glosses denote an entity, quality, or compound.
    return "Noun / compound"


def sanskrit_words(text):
    return [match.group(0) for match in DEVANAGARI_WORD.finditer(text or "")]


def build_fill_blank_options(correct, prompt, corpus_texts, seed=""):
    """Create four unique, morphologically similar Devanagari choices."""
    target = PUNCTUATION.sub("", (correct or "")).strip()
    excluded = set(sanskrit_words(prompt)) | {target}
    counts = Counter(
        word for text in corpus_texts for word in sanskrit_words(text)
        if word not in excluded and len(word) >= 2
    )
    candidates = list(counts)

    def score(candidate):
        suffix = 2 if target[-2:] == candidate[-2:] else 1 if target[-1:] == candidate[-1:] else 0
        length_delta = abs(len(target) - len(candidate))
        return (suffix, -length_delta, min(counts[candidate], 5))

    candidates.sort(key=score, reverse=True)
    chosen = candidates[:3]
    if len(chosen) < 3:
        # Fall back to other text tokens, still keeping all choices unique.
        for candidate in sorted(counts, key=lambda item: (abs(len(item) - len(target)), item)):
            if candidate not in chosen:
                chosen.append(candidate)
            if len(chosen) == 3:
                break
    choices = [target] + chosen
    if len(set(choices)) < 4:
        # The Gita corpus has ample lexical forms; this protects sparse future inputs.
        for fallback in ("धर्मः", "कर्म", "योगः", "आत्मा", "बुद्धिः", "शरीरम्"):
            if fallback not in choices and fallback not in excluded:
                choices.append(fallback)
            if len(choices) == 4:
                break
    random.Random(str(seed)).shuffle(choices)
    return choices[:4]


def build_vocab_options(correct, candidates, grammatical_class, excluded=(), seed="", fallbacks=()):
    """Choose three near lexical distractors of the same broad word class."""
    target = str(correct or "").strip()
    excluded = {str(value).strip().casefold() for value in excluded}
    excluded.add(target.casefold())
    same_class = [
        item["value"] for item in candidates
        if item.get("grammatical_info") == grammatical_class
        and str(item.get("value", "")).strip().casefold() not in excluded
    ]
    pool = same_class or [
        item["value"] for item in candidates
        if str(item.get("value", "")).strip().casefold() not in excluded
    ]
    unique = list(dict.fromkeys(str(value).strip() for value in pool if str(value).strip()))
    target_tokens = set(re.findall(r"[a-zāīūṛṝḷḹṃḥṅñṭḍṇśṣ']+", target.casefold()))

    def similarity(value):
        value_tokens = set(re.findall(r"[a-zāīūṛṝḷḹṃḥṅṭḍṇśṣ']+", value.casefold()))
        shared = len(target_tokens & value_tokens)
        suffix = int(target.casefold()[-2:] == value.casefold()[-2:])
        return shared, suffix, -abs(len(target) - len(value))

    choices = [target] + heapq.nlargest(3, unique, key=similarity)
    for fallback in fallbacks:
        if len(choices) >= 4:
            break
        if fallback.casefold() not in {value.casefold() for value in choices}:
            choices.append(fallback)
    random.Random(str(seed)).shuffle(choices)
    return choices[:4]


def translation_distractors(correct, verse_number, candidate_rows, seed=""):
    """Select nearby, similarly sized translations as plausible alternatives."""
    target = re.sub(r"\s+", " ", str(correct or "")).strip()
    candidates = []
    for row in candidate_rows:
        text = re.sub(r"\s+", " ", str(row["translation_en"] or "")).strip()
        if not text or text.casefold() == target.casefold():
            continue
        distance = abs(int(row["verse_number"]) - int(verse_number))
        candidates.append((abs(len(text) - len(target)), distance, text))
    candidates.sort(key=lambda item: (item[0], item[1]))
    unique = list(dict.fromkeys(item[2] for item in candidates))
    choices = [target] + unique[:3]
    for fallback in (
        "The speaker asks how the assembled warriors will act before the battle begins.",
        "The verse describes a warrior preparing to set aside his weapons and leave the field.",
        "The verse explains why disciplined action should not depend on its future reward.",
    ):
        if len(choices) >= 4:
            break
        if fallback.casefold() not in {value.casefold() for value in choices}:
            choices.append(fallback)
    random.Random(str(seed)).shuffle(choices)
    return choices[:4]
