"""Hold mode for the /app voice loop (page only; no brain change).

When a transcript ends on a "more is coming" signal she waits instead of answering:
  announcer cue  ("ok now listen", "let me tell you something", ...) -> hold until 2 s quiet,
                 an end phrase ("that's it" / "go ahead"), or the 90 s cap;
  connector cue  (ends in and/but/so/um/... or a comma) -> hold for the NEXT chunk only.
Quiet is measured from the END OF SPEECH (the VAD hand-off), so STT latency does not add to it.
Normal turns are untouched. "that's all"/"goodbye" remain the STOP-listening phrases.
Usage: python patch_hold_mode.py [path]   (default: the live page). Idempotent, every anchor asserted."""
import sys
p = sys.argv[1] if len(sys.argv) > 1 else "/opt/layla/web/face/index.html"
s = open(p, encoding="utf-8").read()
if "HOLD MODE (CAPS-HOLD)" in s:
    print("already patched"); sys.exit(0)


def rep(old, new):
    global s
    assert s.count(old) == 1, f"anchor count {s.count(old)}: {old[:70]!r}"
    s = s.replace(old, new, 1)


HOLD_JS = r'''  /* ================= HOLD MODE (CAPS-HOLD) =================
     Wait instead of answering when the transcript signals more is coming. See patch_hold_mode.py. */
  const HOLD_QUIET_MS = 2000, HOLD_CAP_MS = 90000, HOLD_WATCHDOG_MS = 19000;
  const HOLD_END_RE = /(?:^|[\s,.!?])(?:that'?s it|that is it|go ahead|అంతే)[\s.!?]*$/i;
  const HOLD_CUE_RE = /(?:^|[\s,.])(?:ok(?:ay)? now listen|now listen|let me tell you something|i (?:want|need) to tell you something|i have something to tell you|let me explain|let me think|ok(?:ay)? so|so basically|here'?s the thing|the thing is|what i mean is|you know what|hold on|wait(?: a (?:second|sec|moment))?|one (?:more thing|second|sec)|give me a (?:second|sec|moment)|also|and then|by the way|oka nimisham|వినండి|ఒక్క నిమిషం|ఆగండి|ఆగు|చెప్తాను|చెబుతాను)[\s,.…!?]*$/i;
  const HOLD_TRAIL = new Set(['and','but','so','because','then','or','which','that','um','uh','umm','hmm','like','actually','basically','to','of','with','the','a','an']);
  function holdCue(t){
    const s=(t||'').trim(); if(!s) return '';
    if(/^listen[\s.!?]*$/i.test(s)) return 'announce';
    if(HOLD_CUE_RE.test(s)) return 'announce';
    if(/(?:,|…|\.\.\.)\s*$/.test(s)) return 'connector';
    const w=s.toLowerCase().replace(/[^\p{L}\p{N}\s]/gu,' ').split(/\s+/).filter(Boolean);
    if(!w.length) return '';
    if(HOLD_TRAIL.has(w[w.length-1])) return 'connector';
    const last2=w.slice(-2).join(' ');
    return (last2==='you know' || last2==='i mean') ? 'connector' : '';
  }
  let holdBuf='', holdMode='', holdStart=0, holdTimer=null, lastUtterEnd=0;
  function clearHold(){ if(holdTimer){ clearTimeout(holdTimer); holdTimer=null; } holdBuf=''; holdMode=''; holdStart=0; }
  function holdFlush(){
    holdTimer=null;
    const msg=holdBuf.trim(); clearHold();
    if(convo) statusEl.textContent='Conversation — just talk';
    if(msg) ask(msg);
  }
  function holdArm(){
    if(holdTimer) clearTimeout(holdTimer);
    const since=lastUtterEnd ? (Date.now()-lastUtterEnd) : 0;
    holdTimer=setTimeout(holdFlush, Math.max(250, HOLD_QUIET_MS-since));
  }
  // a new chunk of speech has begun: its transcript will re-arm the timer; the watchdog covers noise-only starts
  function holdSpeechStart(){
    if(!holdBuf) return;
    if(holdTimer) clearTimeout(holdTimer);
    holdTimer=setTimeout(holdFlush, HOLD_WATCHDOG_MS);
  }
  function deliver(text){
    const t=(text||'').trim(); if(!t) return;
    const combined = holdBuf ? (holdBuf+' '+t) : t;
    if(HOLD_END_RE.test(combined)){
      const msg=combined.replace(HOLD_END_RE,'').replace(/[\s,]+$/,'').trim();
      clearHold();
      if(convo) statusEl.textContent='Conversation — just talk';
      if(msg) ask(msg); else if(state==='listening') setState('idle');
      return;
    }
    const kind = holdCue(t);
    const capped = holdStart && (Date.now()-holdStart) >= HOLD_CAP_MS;
    const stay = holdBuf && holdMode==='announce';       // already in announcer mode: stay until quiet
    if(!capped && (kind || stay)){
      if(!holdStart) holdStart=Date.now();
      if(kind==='announce' || !holdMode) holdMode = kind==='announce' ? 'announce' : 'connector';
      holdBuf = combined;
      statusEl.textContent='Listening… go on, or say go ahead';
      youEl.innerHTML='<span class="live">'+holdBuf.replace(/&/g,'&amp;').replace(/</g,'&lt;')+'</span>';
      setState('listening'); face('setEmotion', listenFace||'content');
      holdArm();
      return;
    }
    clearHold();
    ask(combined);
  }
'''

# 1. the hold machinery, right before handleFinal
rep("  function handleFinal(text){\n    if(busy) return;", HOLD_JS + "  function handleFinal(text){\n    if(busy) return;")
# 2. route conversation turns + the wake-word remainder through deliver()
rep("    if(convo){ if(STOP_RE.test(text)){ chime(false); endConvo(); return; } ask(text); return; }",
    "    if(convo){ if(STOP_RE.test(text)){ clearHold(); chime(false); endConvo(); return; } deliver(text); return; }")
rep("    if(after.length>1) ask(after);", "    if(after.length>1) deliver(after);")
# 3. Telugu-script wake word (the old \\b regex can't see Telugu letters)
rep("const m=text.match(WAKE_RE); if(!m) return;",
    "const m=text.match(WAKE_RE)||text.match(/లైలా|లైల|లేలా|లీలా|లాయలా|లాఇలా/); if(!m) return;")
# 4. any other way of asking (typed, SSE, stop, mic off) drops a pending hold
rep("    if(!text.trim() || busy) return;\n    busy = true;", "    if(!text.trim() || busy) return;\n    clearHold();\n    busy = true;")
rep("function endConvo(){ convo=false; clearConvoBuffer();", "function endConvo(){ convo=false; clearConvoBuffer(); clearHold();")
rep("micBtn.classList.remove('live'); convo=false; clearConvoBuffer(); sttStop();",
    "micBtn.classList.remove('live'); convo=false; clearConvoBuffer(); clearHold(); sttStop();")
# 5. timing: stamp each chunk with the moment speech ended; note when new speech begins
rep("(f32,sr)=> sttEnqueue({samples:f32, sr, gen:myGen}),", "(f32,sr)=> sttEnqueue({samples:f32, sr, gen:myGen, t:Date.now()}),")
rep("      ()=>{ if(convo && state==='idle') setState('listening'); if(convo) face('setEmotion', listenFace||'content'); },",
    "      ()=>{ holdSpeechStart(); if(convo && state==='idle') setState('listening'); if(convo) face('setEmotion', listenFace||'content'); },")
rep("        if(j.gen!==sttGen || !wakeOn || !text) continue;",
    "        if(!text && holdBuf && j.gen===sttGen && wakeOn){ lastUtterEnd=j.t||Date.now(); holdArm(); }\n"
    "        if(j.gen!==sttGen || !wakeOn || !text) continue;")
rep("        console.log('[stt]', text);\n        handleFinal(text);",
    "        console.log('[stt]', text);\n        lastUtterEnd=j.t||Date.now();\n        handleFinal(text);")

open(p, "w", encoding="utf-8").write(s)
print("hold mode patched")
