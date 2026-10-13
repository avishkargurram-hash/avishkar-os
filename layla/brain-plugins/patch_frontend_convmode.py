"""Page side of conversation mode + sentence-streamed speech ("D").
 - mode_change on  -> conversation stays open, short reactions ("ohh", "ha ha") are kept (min speech 250 ms),
   status shows "Conversation mode"; mode_change off -> her goodbye is spoken, then the conversation closes.
 - speakSmart(): a multi-sentence reply is split into sentences; sentence 1 is synthesised and played at once
   while the next ones are fetched in the background (max 2 in flight), so she starts talking after ONE short
   sentence instead of after the whole reply. Spoken text capped at ~900 chars ("the rest is on your screen").
   Any TTS failure mid-way falls back to the proven single-shot speak() for the remainder.
   Kill switch: set window.LAYLA_CHUNKED_TTS = false.
Usage: python patch_frontend_convmode.py [path]. Idempotent; anchors asserted."""
import sys
p = sys.argv[1] if len(sys.argv) > 1 else "/opt/layla/web/face/index.html"
s = open(p, encoding="utf-8").read()
if "CAPS-CONVMODE" in s:
    print("already patched"); sys.exit(0)


def rep(old, new):
    global s
    assert s.count(old) == 1, f"anchor count {s.count(old)}: {old[:80]!r}"
    s = s.replace(old, new, 1)


JS = r'''  /* ================= CAPS-CONVMODE: conversation mode + sentence-streamed speech ================= */
  window.LAYLA_CHUNKED_TTS = true;
  let companionOn = false;
  function companionUI(on){
    companionOn = !!on;
    try{ VAD_CFG.MIN_SPEECH_MS = on ? 250 : 350; }catch(e){}
    if(on){ convo = true; statusEl.textContent = 'Conversation mode'; }
  }
  const SPEAK_MAX = 900;
  function splitForSpeech(t){
    const s = (t||'').replace(/\s+/g,' ').trim();
    if(s.length < 140) return [s];
    const parts = []; let last = 0, m;
    const re = /([.!?।]+)(\s+)(?=[A-Z"'“0-9ఀ-౿])/g;
    while((m = re.exec(s))){
      const end = m.index + m[1].length;
      const prev = (s.slice(last, end).match(/(\S+)$/) || [''])[0].toLowerCase();
      if(/^(dr|mr|mrs|ms|rs|st|vs|no|sr|jr|e\.g|i\.e|etc)\.$/.test(prev)) continue;
      parts.push(s.slice(last, end).trim()); last = m.index + m[0].length;
    }
    parts.push(s.slice(last).trim());
    const out = [];
    for(const x of parts){ if(!x) continue;
      if(out.length && (out[out.length-1].length < 40 || x.length < 25)) out[out.length-1] += ' ' + x; else out.push(x); }
    let total = 0; const capped = [];
    for(const x of out){ if(total + x.length > SPEAK_MAX && capped.length){ capped.push('The rest is on your screen.'); break; }
      capped.push(x); total += x.length; }
    return capped;
  }
  async function ttsBuf(text, tone){
    const r = await fetch('/tts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text, tone})});
    if(!r.ok) throw new Error('tts '+r.status);
    return await ac().decodeAudioData(await r.arrayBuffer());
  }
  function playBuf(ab){
    return new Promise(res=>{
      const src=ac().createBufferSource(); src.buffer=ab; const an=ac().createAnalyser(); an.fftSize=256;
      freq=new Uint8Array(an.frequencyBinCount); src.connect(an); an.connect(ac().destination);
      src.onended=()=>{ activeAnalyser=null; face('setViseme','M'); res(); };
      setState('speaking'); activeAnalyser=an; visemeTimer=0; requestAnimationFrame(lipLoop); src.start();
    });
  }
  async function speakSmart(text, tone){
    const parts = splitForSpeech(text);
    if(!window.LAYLA_CHUNKED_TTS || parts.length < 2) return speak(text, tone);
    face('setEmotion', TONE_FACE[tone]||'content');
    const bufs = parts.map(()=>null);
    const get = i => (bufs[i] = bufs[i] || ttsBuf(parts[i], tone).catch(()=>null));
    get(0); get(1);
    try{
      for(let i=0; i<parts.length; i++){
        const ab = await get(i);
        if(i+2 < parts.length) get(i+2);
        if(!ab){ await speak(parts.slice(i).join(' '), tone); return; }
        await playBuf(ab);
      }
    } finally {
      activeAnalyser=null; face('setViseme','M'); setState('idle'); settleFace(); muteUntil=Date.now()+800;
    }
  }
'''

rep("  async function ask(text){\n", JS + "  async function ask(text){\n")
rep("      const tone=d.tone||'warm'; listenFace=d.face||'';\n",
    "      const tone=d.tone||'warm'; listenFace=d.face||'';\n"
    "      if(d.mode_change==='on' || d.mode==='companion') companionUI(true);\n")
rep('      await speak(a, tone);  // she finishes "let me look..." completely before anything else happens\n',
    '      await speakSmart(a, tone);  // she finishes "let me look..." completely before anything else happens\n'
    "      if(d.mode_change==='off'){ companionUI(false); try{ chime(false); endConvo(); }catch(e){} }\n")
open(p, "w", encoding="utf-8").write(s)
print("frontend convmode patched")
