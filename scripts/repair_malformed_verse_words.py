"""Repair contaminated word records when the actual verse token is unambiguous.

Most malformed vocabulary rows come from English commentary being mistaken for
Sanskrit. This allowlist only fixes records whose Roman transliteration starts
with an exact word in the verse. It leaves unresolvable records untouched for
review rather than inventing a Sanskrit replacement.
"""

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "database" / "gita_duolingo.db"
SEED_PATH = ROOT / "exports" / "prisma_seed_content.json"

# (verse key, existing transliteration prefix, actual Devanagari, IAST)
REPAIRS = [
    ("BG5.17", "jñānanirdhūtakalmaṣāḥ", "ज्ञाननिर्धूतकल्मषाः", "jñānanirdhūtakalmaṣāḥ"),
    ("BG6.13", "saṁprekṣya", "संप्रेक्ष्य", "saṁprekṣya"),
    ("BG9.34", "māmunto", "मां", "māṃ"),
    ("BG10.23", "yakṣarakṣasām", "यक्षरक्षसाम्", "yakṣarakṣasām"),
    ("BG14.19", "adhigacchati", "अधिगच्छति", "adhigacchati"),
]


def main():
    conn = sqlite3.connect(DB_PATH)
    try:
        changed = 0
        for verse_key, bad_prefix, devanagari, iast in REPAIRS:
            cursor = conn.execute(
                """UPDATE vocabulary
                   SET word_sanskrit = ?, word_transliteration = ?
                   WHERE verse_key = ? AND word_transliteration LIKE ?""",
                (devanagari, iast, verse_key, bad_prefix + "%"),
            )
            if cursor.rowcount not in (0, 1):
                raise RuntimeError(
                    f"Expected one matching word record for {verse_key} ({bad_prefix}); "
                    f"updated {cursor.rowcount}. No changes have been committed."
                )
            changed += cursor.rowcount
            if cursor.rowcount == 0:
                already_fixed = conn.execute(
                    """SELECT COUNT(*) FROM vocabulary
                       WHERE verse_key = ? AND word_sanskrit = ?
                         AND word_transliteration = ?""",
                    (verse_key, devanagari, iast),
                ).fetchone()[0]
                if already_fixed != 1:
                    raise RuntimeError(f"No malformed or repaired row found for {verse_key}.")
        remaining = conn.execute(
            "SELECT COUNT(*) FROM vocabulary WHERE word_sanskrit GLOB '*[A-Za-z]*'"
        ).fetchone()[0]
        conn.commit()
        # Keep the app seed in sync without regenerating its timestamps or causing
        # unrelated content to appear changed.
        seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        verse_ids = {
            row["verseKey"]: row["id"] for row in seed["records"]["verses"]
        }
        seed_changes = 0
        for verse_key, bad_prefix, devanagari, iast in REPAIRS:
            verse_id = verse_ids[verse_key]
            candidates = [
                word for word in seed["records"]["verseWords"]
                if word["verseId"] == verse_id
                and (word.get("transliteration", "").startswith(bad_prefix)
                     or word.get("transliteration") == iast)
            ]
            if len(candidates) != 1:
                raise RuntimeError(
                    f"Expected one seed word for {verse_key}; found {len(candidates)}."
                )
            word = candidates[0]
            if word["sanskrit"] != devanagari or word["transliteration"] != iast:
                word["sanskrit"] = devanagari
                word["transliteration"] = iast
                seed_changes += 1
        SEED_PATH.write_text(
            json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"Repaired {changed} SQLite rows and synchronized {seed_changes} seed rows; "
            f"{remaining} malformed rows remain for review."
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
