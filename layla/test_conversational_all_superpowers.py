"""Conversational ask test verifying all 9 superpowers integrated into Layla.
Calls L.ask() directly through Layla's live runtime.
"""

import json
import sys
import time

sys.path.insert(0, "/opt/layla")
import layla_service as L

def main():
    questions = [
        "What windows are currently open on my PC desktop?",
        "What was I doing on my PC recently according to screen activity history?",
        "Fetch our optimized prompt exemplars for the worldstate domain.",
        "List our pending self-improvement proposals in the sandbox.",
    ]

    for q in questions:
        print("\n" + "=" * 60)
        print(f"USER: {q}")
        print("=" * 60)
        t0 = time.perf_counter()
        try:
            answer = L.ask(q)
            elapsed = time.perf_counter() - t0
            print(f"LAYLA (in {elapsed:.2f}s):")
            print(answer)
        except Exception as exc:
            print("Execution error:", exc)

if __name__ == "__main__":
    main()
