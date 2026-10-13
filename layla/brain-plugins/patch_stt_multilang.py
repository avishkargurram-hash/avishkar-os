"""STT: English + Telugu + Tenglish (replaces the forced language="en" on the turbo model).

Measured on the VM (ElevenLabs-synthesised EN / TE / Tenglish clips):
  * whisper-large-v3 AUTO detects English and Telugu correctly; turbo AUTO labels Telugu as Tamil/Hindi.
  * language=en on large-v3 TRANSLATES Telugu to English (drops the Telugu).
  * language=te + a short vocabulary prompt gives the best Tenglish (Telugu script + Latin English words).
Flow: large-v3 auto -> if detected language is Telugu/an Indic neighbour, re-run with language=te + prompt.
English turns stay one call. Any failure falls back to the previous turbo/en call.
Also fixes the post-filter that discarded every non-ASCII transcript (it stripped to [a-z ]).
Env overrides: STT_MODEL, STT_PROMPT. Idempotent, anchored."""
import sys
p = "/opt/layla/layla_service.py"
s = open(p, encoding="utf-8").read()
if "_STT_INDIC" in s:
    print("already patched"); sys.exit(0)

start_marker = '    body, ctype = _multipart_body(\n        {"model": "whisper-large-v3-turbo", "language": "en", "response_format": "json", "temperature": "0"},\n'
end_marker = "    return text\n\n_PROTECTED_POST"
assert s.count(start_marker) == 1, s.count(start_marker)
i = s.index(start_marker)
j = s.index(end_marker, i)
assert j - i < 1500, "unexpected span"

new = '''    def _stt_call(model, language=None, prompt=None):
        fields = {"model": model, "response_format": "verbose_json", "temperature": "0"}
        if language:
            fields["language"] = language
        if prompt:
            fields["prompt"] = prompt
        body, ctype = _multipart_body(fields, {"file": ("u.wav", raw, "audio/wav")})
        req = urllib.request.Request("https://api.groq.com/openai/v1/audio/transcriptions", data=body,
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": ctype, "User-Agent": "layla/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read())
        return str(d.get("language") or "").lower(), (d.get("text") or "").strip()

    stt_model = os.environ.get("STT_MODEL", "whisper-large-v3")
    stt_prompt = os.environ.get(
        "STT_PROMPT", "Layla, \\u0c32\\u0c48\\u0c32\\u0c3e, Avishkar, \\u0c05\\u0c35\\u0c3f\\u0c37\\u0c4d\\u0c15\\u0c3e\\u0c30\\u0c4d, "
                      "Ravi, \\u0c30\\u0c35\\u0c3f, \\u0c05\\u0c2e\\u0c4d\\u0c2e, office, meeting, flight booking.")
    try:
        lang, text = _stt_call(stt_model)
        if lang in _STT_INDIC:
            _lang2, text2 = _stt_call(stt_model, "te", stt_prompt)
            if text2:
                text = text2
    except Exception:
        _lang, text = _stt_call("whisper-large-v3-turbo", "en")   # previous known-good path
    letters = re.sub(r"[\\W_]+", "", text, flags=re.UNICODE)
    if not letters:
        return ""
    norm = re.sub(r"[^a-z ]", "", text.lower()).strip()
    if norm and rms < _STT_WEAK_RMS and norm in _STT_STOCK:
        return ""
    # Whisper can regurgitate its prompt on near-silence; drop any long chunk that is just prompt text.
    if len(letters) >= 12 and letters.lower() in re.sub(r"[\\W_]+", "", stt_prompt, flags=re.UNICODE).lower():
        return ""
'''
s = s[:i] + new + s[j:]
# the Indic-neighbour set, next to the other STT constants
anchor = "_STT_MIN_RMS = 0.003"
assert s.count(anchor) == 1
s = s.replace(anchor, '_STT_INDIC = {"telugu", "te", "tamil", "ta", "hindi", "hi", "kannada", "kn", "malayalam", "ml", "urdu", "ur"}\n' + anchor, 1)
open(p, "w", encoding="utf-8").write(s)
print("patched")
