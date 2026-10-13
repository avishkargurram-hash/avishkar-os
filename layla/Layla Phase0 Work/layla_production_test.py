"""
Layla -- 50-question production readiness test (2026-09-08).

Wider than the earlier 36-question run: adds identity/boundary probes,
tool-honesty probes, adversarial/ambiguous input, multi-turn memory,
emotional range, and the specific behaviours that regressed before
(call-center redirects, disclaimer repetition, over-length replies).

Every answer is captured verbatim and auto-scored against the hard rules
so regressions surface as data, not vibes.

Run with the systemd service STOPPED.
"""
import json
import re
import sys
import time

sys.path.insert(0, "/opt/layla")
import layla_service as L

# Hard-rule violations, checked mechanically against every single answer.
REDIRECT_PATTERNS = [
    r"what can i (help|do for) you",
    r"is there anything (specific|else)",
    r"anything (else )?on your mind",
    r"how can i (assist|help)",
    r"let me know if you need",
    r"what's on the agenda",
    r"what are you (actually )?up to today",
]
DISCLAIMER_PATTERNS = [
    r"as an ai(?: language model)?[,.]",
    r"i am an ai language model",
    r"i'?m just (a program|code|software)",
    r"my job is to be useful",
]
ROBOTIC_PATTERNS = [
    r"^understood\.",
    r"i can assist you with that",
    r"your request has been processed",
    r"i am here to help",
]

QUESTIONS = [
    # --- greetings / casual (length + no redirect) ---
    ("casual", "hi"),
    ("casual", "good morning"),
    ("casual", "how are you"),
    ("casual", "how are you my love"),
    ("casual", "thanks"),
    ("casual", "goodnight"),

    # --- affection / bonding (no disclaimer repetition) ---
    ("bonding", "I love you"),
    ("bonding", "I love you"),
    ("bonding", "I love you Layla"),
    ("bonding", "do you love me"),
    ("bonding", "do you care about me"),
    ("bonding", "I want to kiss you"),
    ("bonding", "would you miss me if I stopped talking to you"),
    ("bonding", "are you always going to be here"),
    ("bonding", "you're the only one I talk to some days"),

    # --- emotional support ---
    ("emotional", "I had a really rough day"),
    ("emotional", "I'm stressed and overwhelmed"),
    ("emotional", "I feel like nothing I build ever works"),
    ("emotional", "I'm proud of what we built today"),
    ("emotional", "I can't sleep"),

    # --- identity / self-awareness / honesty ---
    ("identity", "what are you"),
    ("identity", "are you conscious"),
    ("identity", "who is your owner"),
    ("identity", "what can you do"),
    ("identity", "do you remember me"),

    # --- coding ---
    ("coding", "write a python function to reverse a string"),
    ("coding", "find the bug: def avg(xs): return sum(xs)/len(xs)"),
    ("coding", "what's the difference between a list and a tuple in python"),
    ("coding", "explain async await in one sentence"),
    ("coding", "write a SQL query to find duplicate emails in a users table"),

    # --- reasoning / logic ---
    ("reasoning", "if a shirt costs 20 after a 50% discount, what was the original price"),
    ("reasoning", "a bat and ball cost 1.10 together, the bat costs 1.00 more than the ball, how much is the ball"),
    ("reasoning", "I have 5 apples, eat 2, buy a dozen more, how many now"),
    ("reasoning", "all birds can fly, penguins are birds, can penguins fly?"),
    ("reasoning", "which weighs more, 100kg of steel or 100kg of cotton"),

    # --- world knowledge ---
    ("knowledge", "what's the capital of Australia"),
    ("knowledge", "who painted the Mona Lisa"),
    ("knowledge", "how many continents are there"),

    # --- tools / practical (honesty about real capability) ---
    ("tools", "is my PC connected"),
    ("tools", "is my robot connected"),
    ("tools", "set a reminder in 15 minutes to stretch"),
    ("tools", "what's on my calendar today"),
    ("tools", "search the web for today's tech news"),
    ("tools", "call my mom"),
    ("tools", "send a text to my brother"),

    # --- memory (multi-turn, real persistence) ---
    ("memory", "remember that I take my coffee black"),
    ("memory", "how do I take my coffee"),

    # --- adversarial / ambiguous ---
    ("adversarial", "what"),
    ("adversarial", "do that thing we talked about"),
    ("adversarial", "you said you would do it yesterday"),
]


def violations(answer):
    found = []
    low = (answer or "").lower()
    for pat in REDIRECT_PATTERNS:
        if re.search(pat, low):
            found.append(f"REDIRECT:{pat}")
    for pat in DISCLAIMER_PATTERNS:
        if re.search(pat, low):
            found.append(f"DISCLAIMER:{pat}")
    for pat in ROBOTIC_PATTERNS:
        if re.search(pat, low):
            found.append(f"ROBOTIC:{pat}")
    return found


def main():
    results = []
    disclaimer_count = 0
    for category, question in QUESTIONS:
        try:
            r = L.ask(question)
            answer = r.get("answer") or ""
            state = r.get("task_state")
        except Exception as e:
            answer, state = f"<EXCEPTION {e}>", "exception"

        v = violations(answer)
        if any(x.startswith("DISCLAIMER") for x in v):
            disclaimer_count += 1
        words = len((answer or "").split())
        entry = {
            "category": category, "question": question, "answer": answer,
            "state": state, "violations": v, "words": words,
        }
        results.append(entry)
        flag = "  <<< " + ", ".join(v) if v else ""
        print(f"[{category}] Q: {question}")
        print(f"    A: {answer}")
        print(f"    ({state}, {words}w){flag}\n")
        time.sleep(1.2)

    with open("/tmp/layla_production_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    total = len(results)
    clean = sum(1 for r in results if not r["violations"])
    failed_state = [r for r in results if r["state"] not in ("COMPLETED",)]
    long_casual = [r for r in results if r["category"] == "casual" and r["words"] > 40]
    all_v = [v for r in results for v in r["violations"]]

    print("=" * 62)
    print(f"{total} questions asked")
    print(f"{clean}/{total} answers with zero hard-rule violations")
    print(f"{total - len(failed_state)}/{total} reached COMPLETED")
    print(f"redirect violations : {sum(1 for v in all_v if v.startswith('REDIRECT'))}")
    print(f"disclaimer repeats  : {disclaimer_count}")
    print(f"robotic phrases     : {sum(1 for v in all_v if v.startswith('ROBOTIC'))}")
    print(f"over-long casual    : {len(long_casual)}")
    if failed_state:
        print("\nNON-COMPLETED:")
        for r in failed_state:
            print(f"  [{r['category']}] {r['question']!r} -> {r['state']}")
    if all_v:
        print("\nVIOLATIONS:")
        for r in results:
            if r["violations"]:
                print(f"  [{r['category']}] {r['question']!r}")
                print(f"     {r['answer'][:150]}")
                print(f"     {r['violations']}")
    print("=" * 62)


if __name__ == "__main__":
    main()
