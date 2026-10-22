"""Frontend for Task 1 #4 (visemes + expressions), #7 (backchannel / dual-track)
and the shared approval cards (#11). Anchored patch of web/face/index.html."""
import sys
p = "/opt/layla/web/face/index.html"
s = open(p, encoding="utf-8").read()
if "CAPS-3-11" in s:
    print("already patched"); sys.exit(0)

def rep(old, new):
    global s
    assert s.count(old) == 1, f"anchor count {s.count(old)} for {old[:70]!r}"
    s = s.replace(old, new, 1)

# ---- #4a: spectral visemes instead of a random open shape ----
rep("""  function visemeFor(a){ if(a<0.05)return 'M'; if(a<0.13)return 'E'; if(a<0.26)return 'S'; return OPEN[(Math.random()*OPEN.length)|0]; }""",
"""  /* CAPS-3-11 #4: viseme from the audio spectrum, not a random pick. Bins are
     ~sampleRate/256 wide (~187 Hz at 48 kHz): low = jaw/round vowels (O,U),
     mid = open/spread vowels (A,E), high = sibilants (S/F). */
  function visemeFor(a){
    if(a<0.045) return 'M';
    const n=freq.length, hz=(ac().sampleRate/2)/n;
    let lo=0,mid=0,hi=0;
    for(let i=0;i<n;i++){ const f=i*hz, v=freq[i];
      if(f<800) lo+=v; else if(f<2600) mid+=v; else if(f<8000) hi+=v; }
    const t=lo+mid+hi+1e-6, h=hi/t, l=lo/t;
    if(h>0.42) return a>0.2?'S':'F';
    if(l>0.62) return a>0.2?'O':'U';
    if(a<0.12) return 'N';
    return a>0.24?'A':'E';
  }""")

# ---- #4b: expression follows her tone, and his mood while she listens ----
rep("""  function speak(text, tone){
    return new Promise(async (resolve)=>{""",
"""  const TONE_FACE={warm:'content',playful:'smile',excited:'excited',calm:'content',serious:'neutral',sympathetic:'concerned'};
  let listenFace='';
  function settleFace(){ face('setEmotion', listenFace||'idle'); }
  function speak(text, tone){
    face('setEmotion', TONE_FACE[tone]||'content');
    return new Promise(async (resolve)=>{""")
rep("""        src.onended=()=>{activeAnalyser=null;face('setViseme','M');setState('idle');muteUntil=Date.now()+800;resolve();};""",
"""        src.onended=()=>{activeAnalyser=null;face('setViseme','M');setState('idle');settleFace();muteUntil=Date.now()+800;resolve();};""")

# ---- #7: dual-track -- a quick spoken acknowledgement while the brain works ----
rep("""  async function ask(text){
    if(!text.trim() || busy) return;
    busy = true;
    youEl.innerHTML='“'+text+'”'; laylaEl.textContent='…'; setState('thinking');
    try{
      const r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text})});""",
"""  /* CAPS-3-11 #7: fillers are synthesised once (her real voice) and cached in
     localStorage, so a slow turn gets an instant "one sec" instead of silence. */
  const FILLERS={act:'One sec, on it.',look:'Okay, let me check.',think:'Hmm, let me think.',soft:'Mm-hm.'};
  const fillerBuf={};
  async function loadFiller(k){
    if(fillerBuf[k]) return fillerBuf[k];
    const key='layla-filler-v1-'+k; let b64=null;
    try{ b64=localStorage.getItem(key); }catch(e){}
    if(!b64){
      const r=await fetch('/tts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:FILLERS[k],tone:'calm'})});
      if(!r.ok) return null;
      const bytes=new Uint8Array(await r.arrayBuffer()); b64=bytesToBase64(bytes);
      try{ localStorage.setItem(key,b64); }catch(e){}
    }
    const bin=atob(b64), u=new Uint8Array(bin.length); for(let i=0;i<bin.length;i++) u[i]=bin.charCodeAt(i);
    fillerBuf[k]=await ac().decodeAudioData(u.buffer); return fillerBuf[k];
  }
  function fillerKind(t){
    if(/\\b(turn|switch|open|play|send|call|message|set|remind|schedule|start|stop)\\b/i.test(t)) return 'act';
    if(/\\b(check|weather|news|search|find|look|see|what's on|calendar|email|status)\\b/i.test(t)) return 'look';
    if(t.split(/\\s+/).length>12 || /\\b(why|how|explain|should i|what do you think)\\b/i.test(t)) return 'think';
    return 'soft';
  }
  function playFiller(k){
    return new Promise(async res=>{
      try{ const buf=await loadFiller(k); if(!buf) return res();
        const src=ac().createBufferSource(); src.buffer=buf; const an=ac().createAnalyser(); an.fftSize=256;
        src.connect(an); an.connect(ac().destination); activeAnalyser=an; freq=new Uint8Array(an.frequencyBinCount);
        requestAnimationFrame(lipLoop); src.onended=()=>{ activeAnalyser=null; face('setViseme','M'); res(); }; src.start();
      }catch(e){ res(); }
    });
  }
  async function ask(text){
    if(!text.trim() || busy) return;
    busy = true;
    youEl.innerHTML='“'+text+'”'; laylaEl.textContent='…'; setState('thinking'); face('setEmotion','thinking');
    let fillerP=null; const fillerT=setTimeout(()=>{ fillerP=playFiller(fillerKind(text)); }, 1300);
    try{
      const r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text})});
      clearTimeout(fillerT); if(fillerP) await fillerP;""")
rep("""      const tone=d.tone||'warm';""",
"""      const tone=d.tone||'warm'; listenFace=d.face||'';""")
rep("""    }catch(e){ laylaEl.textContent='I could not reach my brain just now.'; setState('idle'); }
    finally{ busy = false; }""",
"""    }catch(e){ clearTimeout(fillerT); laylaEl.textContent='I could not reach my brain just now.'; setState('idle'); settleFace(); }
    finally{ busy = false; }""")
# warm the filler cache on the first tap (autoplay-safe)
rep("""  addEventListener('pointerdown',function once(){removeEventListener('pointerdown',once);ac().resume&&ac().resume();},{once:true});""",
"""  addEventListener('pointerdown',function once(){removeEventListener('pointerdown',once);ac().resume&&ac().resume();
    setTimeout(()=>{ Object.keys(FILLERS).reduce((p,k)=>p.then(()=>loadFiller(k).catch(()=>{})),Promise.resolve()); },1500);},{once:true});""")
# #7 visual backchannel: attentive face the moment he starts talking
rep("""      ()=>{ if(convo && state==='idle') setState('listening'); },""",
"""      ()=>{ if(convo && state==='idle') setState('listening'); if(convo) face('setEmotion', listenFace||'content'); },""")

# ---- approval cards (#11 messages to people; #10 later) ----
rep("""        } else if(t==='screen'){ try{ window.__layla_screen && window.__layla_screen(m); }catch(_){}
        }""",
"""        } else if(t==='screen'){ try{ window.__layla_screen && window.__layla_screen(m); }catch(_){}
        } else if(t==='approval'){ try{ window.__layla_approval && window.__layla_approval(m); }catch(_){}
        } else if(t==='approval_closed'){ try{ window.__layla_approval_close && window.__layla_approval_close(m.id); }catch(_){}
        }""")
rep("""  </script>
</body>""",
"""  /* ============ approval cards (CAPS-3-11) ============
     Anything that reaches outside Layla (a message to another person) waits
     for an explicit Allow here or a spoken yes. Nothing is sent from a card
     the owner didn't tap. */
  (function(){
    const box=document.createElement('div');
    box.style.cssText='position:fixed;top:70px;right:18px;z-index:99998;display:flex;flex-direction:column;gap:10px;width:min(360px,90vw)';
    document.body.appendChild(box);
    const cards={};
    function esc(t){ const d=document.createElement('div'); d.textContent=t||''; return d.innerHTML; }
    window.__layla_approval=function(m){
      if(!m||!m.id||cards[m.id]) return;
      const c=document.createElement('div');
      c.style.cssText='background:#0b0f16;border:1px solid rgba(53,224,200,.45);border-radius:12px;padding:12px 14px;box-shadow:0 12px 36px rgba(0,0,0,.6);color:#e9edf4;font-size:13.5px';
      c.innerHTML='<div style="font-weight:700;color:#35e0c8;margin-bottom:6px">'+esc(m.title)+'</div>'+
        '<div style="white-space:pre-wrap;color:#c8ceda;max-height:160px;overflow:auto;margin-bottom:10px">'+esc(m.detail)+'</div>'+
        '<div style="display:flex;gap:8px;justify-content:flex-end"><button data-a="0" style="background:none;border:1px solid #3a4352;color:#c8ceda;border-radius:8px;padding:7px 14px;cursor:pointer">Deny</button>'+
        '<button data-a="1" style="background:#35e0c8;border:none;color:#04120f;font-weight:700;border-radius:8px;padding:7px 16px;cursor:pointer">Allow</button></div>';
      c.querySelectorAll('button').forEach(b=>b.addEventListener('click',async()=>{
        c.style.opacity='.5'; c.querySelectorAll('button').forEach(x=>x.disabled=true);
        try{ await fetch('/approval/decide',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:m.id,allow:b.dataset.a==='1'})}); }catch(e){}
        window.__layla_approval_close(m.id);
      }));
      cards[m.id]=c; box.appendChild(c); chime(true);
      setTimeout(()=>window.__layla_approval_close(m.id), ((m.expires_in||600)+5)*1000);
    };
    window.__layla_approval_close=function(id){ const c=cards[id]; if(c){ c.remove(); delete cards[id]; } };
    fetch('/approval/pending').then(r=>r.ok?r.json():[]).then(l=>(l||[]).forEach(window.__layla_approval)).catch(()=>{});
  })();
  </script>
</body>""")

open(p, "w", encoding="utf-8").write(s)
print("patched")
