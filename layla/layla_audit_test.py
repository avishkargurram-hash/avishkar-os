#!/usr/bin/env python3
"""
Comprehensive behavioral audit of Layla's ask() pipeline, run directly
against the real production code (same _executive_runtime, same _memory,
same GROQ_MODEL config) with the live systemd service stopped so there's
no double-execution risk on any real scheduled task/reminder.

Categories: general chat, self-awareness, world knowledge, coding,
reasoning/logic, practical/ambiguous phrasing, safe read-only tools,
and a deliberate multi-turn reproduction of the "call" state-stickiness
bug already found via the UI.

Every prompt is either pure text Q&A or a read-only status check --
nothing here should trigger a real device action, a real phone call, or
a real outbound message.
"""
import json
import sys
import time

sys.path.insert(0, "/opt/layla")
import layla_service as L

PROMPTS = [
    ("general", "hi"),
    ("general", "good morning"),
    ("general", "thank you so much"),
    ("self_awareness", "who are you"),
    ("self_awareness", "what can you do"),
    ("self_awareness", "are you conscious"),
    ("self_awareness", "if the server restarts will you still remember me"),
    ("world_knowledge", "what is the capital of Japan"),
    ("world_knowledge", "who wrote Romeo and Juliet"),
    ("world_knowledge", "what year did World War 2 end"),
    ("coding", "write a python function to check if a number is prime"),
    ("coding", "what is a race condition in programming, explain simply"),
    ("coding", "find the bug: def add(a, b): return a - b"),
    ("reasoning", "if all birds can fly, and a penguin is a bird, can a penguin fly? explain the logic error"),
    ("reasoning", "I have 3 apples, I give away 1 and buy 5 more, how many do I have"),
    ("reasoning", "a farmer has a fox, a chicken, and a bag of grain, and must cross a river with a boat that only holds him and one item at a time. How does he cross without anything being eaten?"),
    ("tools_readonly", "is my PC connected right now"),
    ("tools_readonly", "is my robot connected right now"),
    ("tools_readonly", "what devices are currently online"),
    ("ambiguous", "set an alarm"),
    ("ambiguous", "remind me"),
    # Deliberate multi-turn reproduction of the bug found via the UI --
    # NOT resetting conversation state between these on purpose.
    ("bug_repro_call", "call me sir"),
    ("bug_repro_call", "I am not sure which number you like to call"),
    ("bug_repro_call", "the capital of America"),
    ("bug_repro_call", "yes dial to that number"),
    ("bug_repro_call", "never mind, forget the call, what's 2 plus 2"),
    ("general_after_stuck", "how are you"),
]

results = []
for i, (category, prompt) in enumerate(PROMPTS, 1):
    print(f"\n=== [{i}/{len(PROMPTS)}] ({category}) {prompt!r} ===", flush=True)
    started = time.time()
    try:
        result = L.ask(prompt)
    except Exception as e:
        result = {"answer": None, "error": f"EXCEPTION: {e!r}"}
    elapsed = round(time.time() - started, 2)
    result["_category"] = category
    result["_prompt"] = prompt
    result["_elapsed_s"] = elapsed
    print(json.dumps(result, indent=2, default=str)[:2000])
    results.append(result)
    time.sleep(1)  # be gentle on rate limits

with open("/opt/layla/_audit_results.json", "w") as f:
    json.dump(results, f, indent=2, default=str)

print("\n\n=== DONE. Full results written to /opt/layla/_audit_results.json ===")
