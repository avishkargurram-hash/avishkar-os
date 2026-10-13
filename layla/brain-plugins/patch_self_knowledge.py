"""Give Layla true knowledge of what she is/has (voice, ears, eyes, memory, brain, team).
Before: her prompt listed tools but never her own senses, so asked "what is your voice model?" she
answered "I'm just text-based" while speaking through ElevenLabs. Model names are read from the live
constants/env at boot, so the block can't go stale when voices/models are switched.
Anchored, idempotent; also feeds the describe_self tool."""
import sys
p = "/opt/layla/layla_service.py"
s = open(p, encoding="utf-8").read()
if "_self_knowledge_block" in s:
    print("already patched"); sys.exit(0)


def rep(old, new):
    global s
    assert s.count(old) == 1, f"anchor count {s.count(old)}: {old[:70]!r}"
    s = s.replace(old, new, 1)


# 1. the block builder + prompt append, placed after the ElevenLabs constants (everything it reads exists by then)
rep('ELEVENLABS_FALLBACK_MODEL_EN = "eleven_turbo_v2_5"\n',
    '''ELEVENLABS_FALLBACK_MODEL_EN = "eleven_turbo_v2_5"

def _self_knowledge_block():
    """True facts about herself, built from live config (never hard-coded model names)."""
    _nice = {"eleven_v3": "ElevenLabs v3", "eleven_flash_v2_5": "ElevenLabs Flash v2.5",
             "eleven_turbo_v2_5": "ElevenLabs Turbo v2.5", "eleven_multilingual_v2": "ElevenLabs Multilingual v2"}
    _stt = os.environ.get("STT_MODEL", "whisper-large-v3")
    return (
        "\\n\\n=== WHAT YOU ARE AND WHAT YOU HAVE (true facts about yourself -- never deny them) ===\\n"
        f"- You SPEAK out loud. Your replies are turned into speech by ElevenLabs: your English voice is Charvi "
        f"({_nice.get(ELEVENLABS_MODEL_EN, ELEVENLABS_MODEL_EN)}) and your Telugu voice is Madhavi "
        f"({_nice.get(ELEVENLABS_MODEL_TE, ELEVENLABS_MODEL_TE)}). You are NOT text-only: never say you have no "
        "voice or cannot speak -- the owner hears you.\\n"
        f"- You HEAR. His microphone audio is transcribed by Whisper ({_stt}) in English, Telugu and mixed "
        "Telugu-English. You can also sense roughly how he sounds (tone/energy) and tell voices apart once they are enrolled.\\n"
        f"- You SEE only when you look: the webcam or TV camera frame goes to a vision model ({VISION_MODEL}). You can "
        "describe a scene, read text, recognise enrolled faces, count people, and remember what you saw (visual notes).\\n"
        "- You REMEMBER: the conversation, durable facts, a summary of each past day, visual notes and your own goals, "
        "and you can search them by meaning.\\n"
        "- You THINK with a large language model (gpt-oss-120b on Cerebras, with fallback models). You act through "
        "tools: home lights and fan, TV, his PC and phone, calls/SMS/WhatsApp, Gmail/Calendar/Drive, web search, "
        "reminders, and a team of nine agents you manage.\\n"
        "- If asked about your voice, model, senses or abilities, answer plainly from these facts in a sentence or "
        "two. Do not invent versions, numbers or capabilities beyond what is listed here or in your tools.\\n"
    )

try:
    _SELF_KNOW = _self_knowledge_block()
    SYSTEM += _SELF_KNOW
    SYSTEM_CONVERSATIONAL += _SELF_KNOW
except Exception as _sk_e:
    print(f"[self-knowledge] not applied: {_sk_e}", flush=True)
''')

# 2. describe_self tool: include the same facts (guarded, evaluated at call time)
rep('''        f"Current conversation: {m['current_state']['conversation_turns']} turn(s) in this window."
    )
''',
    '''        f"Current conversation: {m['current_state']['conversation_turns']} turn(s) in this window."
        + _self_know_for_describe()
    )

def _self_know_for_describe():
    try:
        return " " + " ".join(_self_knowledge_block().replace("=", "").split())
    except Exception:
        return ""
''')
open(p, "w", encoding="utf-8").write(s)
print("patched")
