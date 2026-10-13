"""Surgically removes the spoken backchannel filler (Task 1 #7) from web/face/index.html.
Keeps: spectral visemes (#4), tone->expression, thinking face, attentive listening face, approval cards.
Idempotent; every cut is anchored and asserted."""
import sys
p = "/opt/layla/web/face/index.html"
s = open(p, encoding="utf-8").read()
if "playFiller" not in s and "FILLERS" not in s:
    print("already removed"); sys.exit(0)

def cut(start, end, keep_end=True):
    global s
    assert s.count(start) == 1, f"start anchor count {s.count(start)}: {start[:50]!r}"
    i = s.index(start)
    j = s.index(end, i)
    s = s[:i] + (s[j:] if keep_end else s[j + len(end):])

def rep(old, new):
    global s
    assert s.count(old) == 1, f"anchor count {s.count(old)}: {old[:60]!r}"
    s = s.replace(old, new, 1)

# 1. the filler clips + player (everything between its comment and `async function ask`)
cut("  /* CAPS-3-11 #7: fillers are synthesised once", "  async function ask(text){")
# 2. the 1.3 s timer and the wait-for-filler inside ask()
rep("    let fillerP=null; const fillerT=setTimeout(()=>{ fillerP=playFiller(fillerKind(text)); }, 1300);\n", "")
rep("      clearTimeout(fillerT); if(fillerP) await fillerP;\n", "")
rep("    }catch(e){ clearTimeout(fillerT); laylaEl.textContent='I could not reach my brain just now.';",
    "    }catch(e){ laylaEl.textContent='I could not reach my brain just now.';")
# 3. the first-tap cache warm-up
rep("""addEventListener('pointerdown',function once(){removeEventListener('pointerdown',once);ac().resume&&ac().resume();
    setTimeout(()=>{ Object.keys(FILLERS).reduce((p,k)=>p.then(()=>loadFiller(k).catch(()=>{})),Promise.resolve()); },1500);},{once:true});""",
    "addEventListener('pointerdown',function once(){removeEventListener('pointerdown',once);ac().resume&&ac().resume();},{once:true});")

assert "playFiller" not in s and "FILLERS" not in s and "fillerT" not in s and "loadFiller" not in s
open(p, "w", encoding="utf-8").write(s)
print("filler removed")
