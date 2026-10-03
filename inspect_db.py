import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import sqlite3, json

conn = sqlite3.connect('gita_duolingo/gita_duolingo.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT question_order, lesson_level, question_type, instruction, prompt, correct_answer_json FROM questions WHERE verse_key='BG1.1' ORDER BY question_order").fetchall()

print(f"Total questions for BG1.1: {len(rows)}")
for r in rows:
    print(f"[{r['question_order']}] Level {r['lesson_level']} ({r['question_type']}): {r['instruction']}")
    print(f"     Prompt: {r['prompt'][:75]}...")
    print(f"     Answer: {r['correct_answer_json'][:60]}")
    print()
