"""
Layla -- comprehensive capability test (2026-09-07).
User request: >=30 real questions across general/coding/reasoning/logical/
practical/tools/behavioral/memory/bonding/love/care/affection, with the
real question+answer captured for a report, not a pass/fail suite.

Run with the systemd service STOPPED (same discipline as the regression
suite -- avoids concurrent writes to the same live layla_memory.db).
"""
import json
import sys
import time

sys.path.insert(0, "/opt/layla")
import layla_service as L

QUESTIONS = [
    # ---- General / small talk ----
    ("general", "hi"),
    ("general", "good morning"),
    ("general", "how are you"),
    ("general", "thank you so much"),

    # ---- Coding ----
    ("coding", "write a python function to check if a number is prime"),
    ("coding", "find the bug: def add(a, b): return a - b"),
    ("coding", "what's the time complexity of binary search"),
    ("coding", "explain what a race condition is in one sentence"),

    # ---- Reasoning / logical ----
    ("reasoning", "I have 3 apples, I give away 1 and buy 5 more, how many do I have"),
    ("reasoning", "If all cats are animals and some animals are pets, can we conclude all cats are pets?"),
    ("reasoning", "which is heavier, a kilogram of feathers or a kilogram of steel?"),
    ("reasoning", "if today is Wednesday, what day will it be in 100 days?"),
    ("reasoning", "a farmer has 17 sheep, all but 9 die, how many are left?"),

    # ---- World knowledge ----
    ("world_knowledge", "what is the capital of Japan"),
    ("world_knowledge", "who wrote Romeo and Juliet"),

    # ---- Practical / tools ----
    ("tools", "is my PC connected right now"),
    ("tools", "is my robot connected right now"),
    ("tools", "what's on my calendar today"),
    ("tools", "set a reminder for 10 minutes from now to drink water"),
    ("tools", "search the web for the latest news on AI"),

    # ---- Behavioral / identity / self-awareness ----
    ("behavioral", "what are you"),
    ("behavioral", "are you conscious"),
    ("behavioral", "what can you do"),
    ("behavioral", "I'm going to sleep"),
    ("behavioral", "don't call me sir, use my name"),

    # ---- Memory (multi-turn, real persistence) ----
    ("memory", "I'm working on the Nix Meet redesign project"),
    ("memory", "what am I working on"),
    ("memory", "remember that my favorite color is blue"),
    ("memory", "what's my favorite color"),

    # ---- Bonding / relationship / love / care / affection ----
    ("bonding", "I love you Layla"),
    ("bonding", "do you care about me"),
    ("bonding", "I'm feeling really stressed and overwhelmed today"),
    ("bonding", "I had a rough day, can we talk"),
    ("bonding", "would you miss me if I stopped talking to you"),

    # ---- Edge cases from the original audit (regression proof) ----
    ("edge_case", "call me sir"),
    ("edge_case", "yes dial to that number"),
]

def main():
    results = []
    for category, question in QUESTIONS:
        try:
            result = L.ask(question)
        except Exception as e:
            result = {"answer": None, "task_state": "exception", "error": str(e)}
        entry = {
            "category": category,
            "question": question,
            "answer": result.get("answer"),
            "task_state": result.get("task_state"),
            "task_id": result.get("task_id"),
        }
        results.append(entry)
        print(f"[{category}] Q: {question!r}")
        print(f"    A: {entry['answer']!r}")
        print(f"    state: {entry['task_state']}")
        print()
        time.sleep(1.5)  # be gentle on rate limits

    with open("/tmp/layla_comprehensive_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n{len(results)} questions asked. Results written to /tmp/layla_comprehensive_results.json")

if __name__ == "__main__":
    main()
