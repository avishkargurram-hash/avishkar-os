"""Bug sweep 2 (2026-10-12): question-shaped tool requests were answered WITHOUT tools.
"How is the weather in Hyderabad?" has no action verb and no capability-domain match, so the Phase-2 intent
gate sent it down the no-tools path, where gpt-oss wrote a fake web call as text. The real get_weather tool
(WAE) and the new question-type tools (where are my keys / my mood / who is speaking / how are my agents /
health data / my goals / outbox) were unreachable the same way.
  K. intent gate: a keyword match on those tool categories routes the turn to the tool path
  L. tool loop: after a recovered (text-faked) call is really executed, tell the model to answer from the
     results instead of faking another call (it was looping to "I couldn't complete that...").
Usage: python patch_bugsweep2.py [path]. Idempotent; anchors asserted."""
import sys
p = sys.argv[1] if len(sys.argv) > 1 else "/opt/layla/layla_service.py"
s = open(p, encoding="utf-8").read()
if "_question_tool_match" in s:
    print("already patched"); sys.exit(0)


def rep(old, new):
    global s
    assert s.count(old) == 1, f"anchor count {s.count(old)}: {old[:80]!r}"
    s = s.replace(old, new, 1)


rep("def _layla_respond_fn(task):\n",
    '''# Tool categories whose requests are QUESTIONS (no action verb), so the intent gate can't see them.
_QUESTION_TOOL_CATS = ("world", "visionmem", "affect", "speakers", "l365", "telemetry", "ambient", "social")

def _question_tool_match(text):
    t = (text or "").lower()
    try:
        return any(_CATEGORY_PATTERNS[c].search(t) for c in _QUESTION_TOOL_CATS if c in _CATEGORY_PATTERNS)
    except Exception:
        return False

def _layla_respond_fn(task):
''')
rep('''                          or _PERSONAL_DATA_RE.search(task.input or ""))
        answer, _tool_records, _cost, _pending_actions = _run_conversational_turn(task, use_tools=_use_tools)
''',
    '''                          or _PERSONAL_DATA_RE.search(task.input or "")
                          or _question_tool_match(task.input or ""))
        answer, _tool_records, _cost, _pending_actions = _run_conversational_turn(task, use_tools=_use_tools)
''')
rep('''            if visual_capture_placeholder:
                # Never let the model narrate here''',
    '''            if any(str(tc.get("id", "")).startswith("recovered-") for tc in tool_calls):
                messages.append({"role": "system", "content":
                    "You now have the real tool results above. Answer the owner directly, in one or two plain "
                    "spoken sentences, using them. Do not write tool calls, JSON, or your plan."})
            if visual_capture_placeholder:
                # Never let the model narrate here''')
open(p, "w", encoding="utf-8").write(s)
print("bugsweep2 patched")
