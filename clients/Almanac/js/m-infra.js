/* Almanac infrastructure modules: native alarms, the live WebSocket link (cross-device clipboard) and Family Connect.
   Loaded after m-core.js; reads config through the globals syncCfg()/syncConfigured()/syncFetch()/syncPullState(). */
(function(root){
  'use strict';
  const A = root.ALM;
  const $ = A.$, E = A.E, J = A.J;
  const val = id => { const e = $(id); return e ? e.value : ''; };
  const clip = (s, n) => String(s == null ? '' : s).trim().slice(0, n);
  const lsGet = k => { try{ return localStorage.getItem(k); }catch(e){ return null; } };
  const lsSet = (k, v) => { try{ localStorage.setItem(k, v); }catch(e){} };
  const pad2 = n => String(n).padStart(2, '0');
  const ld = d => d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
  const cfg = () => (typeof syncCfg === 'function') ? syncCfg() : null;
  const configured = () => (typeof syncConfigured === 'function') ? !!syncConfigured() : false;
  const h32 = s => { let h = 0x811c9dc5; for(let i = 0; i < s.length; i++){ h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; };
  const nid = s => ((h32(s) & 0x7fffffff) || 1);
  const native = () => { try{ const c = root.Capacitor; return !!(c && c.isNativePlatform && c.isNativePlatform()); }catch(e){ return false; } };
  const LN = () => { try{ return native() && root.Capacitor.Plugins && root.Capacitor.Plugins.LocalNotifications || null; }catch(e){ return null; } };
  const view = () => (typeof currentView !== 'undefined') ? currentView : '';
  const modOpen = id => view() === 'mod' && A.cur === id;
  async function api(path, opts){
    const c = cfg(); if(!c || !c.token) throw new Error('Connect to your Layla server first');
    const o = Object.assign({}, opts);
    if(o.body && typeof o.body !== 'string') o.body = JSON.stringify(o.body);
    if(o.body) o.headers = Object.assign({ 'Content-Type':'application/json' }, o.headers);
    return syncFetch(c, path, o);
  }
  const errMsg = e => e && e.status === 403 ? 'Only the owner can do that' : (e && e.message) || 'Something went wrong';

  const devLabel = (() => {
    let id = lsGet('almanac_dev_label');
    if(!id){
      let plat = 'web'; try{ plat = (root.Capacitor && root.Capacitor.getPlatform && root.Capacitor.getPlatform()) || 'web'; }catch(e){}
      id = plat + '-' + Math.random().toString(36).slice(2, 6); lsSet('almanac_dev_label', id);
    }
    return id;
  })();
  const DAYN = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'], DAYL = ['S','M','T','W','T','F','S'];

  /* ============================================================ ALARMS ============================================================
     Record: { label, time:'HH:MM', days:[0..6] (0=Sun), on, once?:'YYYY-MM-DD' }. No days = a one-shot alarm; `once` pins the date it will
     ring on, so it does not slide to tomorrow after it fires. Native: Capacitor Local Notifications on a high-importance channel.
     Web: an in-page ring while Almanac is open. */
  const AL = root.AL = { perm:{ display:'unknown', exact:'unknown' }, rung:{}, snoozes:[], busy:false, again:false, inited:false, ringing:null, beepT:null, ctx:null };
  const CH = 'almanac-alarm', SIG_KEY = 'almanac_alarm_sig', IDS_KEY = 'almanac_alarm_ids', RUNG_KEY = 'almanac_alarm_rung', SNZ_KEY = 'almanac_alarm_snooze';
  const SNOOZE_MIN = 9;
  try{ AL.rung = JSON.parse(lsGet(RUNG_KEY) || '{}') || {}; }catch(e){ AL.rung = {}; }
  try{ AL.snoozes = JSON.parse(lsGet(SNZ_KEY) || '[]') || []; }catch(e){ AL.snoozes = []; }

  const parseTime = t => { const m = /^(\d{2}):(\d{2})$/.exec(t || ''); if(!m) return null; const h = +m[1], mi = +m[2]; return (h < 24 && mi < 60) ? [h, mi] : null; };
  const cleanDays = d => Array.from(new Set((Array.isArray(d) ? d : []).filter(x => Number.isInteger(x) && x >= 0 && x <= 6))).sort();
  AL.parseTime = parseTime;

  /* Next time this alarm will ring strictly after `from`, or null. */
  AL.next = (a, from) => {
    const tm = parseTime(a.time); if(!tm) return null; from = from || new Date();
    const days = cleanDays(a.days);
    if(!days.length){
      if(!a.once) { for(let i = 0; i < 2; i++){ const d = new Date(from.getFullYear(), from.getMonth(), from.getDate() + i, tm[0], tm[1], 0, 0); if(d > from) return d; } return null; }
      const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(a.once); if(!m) return null;
      const d = new Date(+m[1], +m[2] - 1, +m[3], tm[0], tm[1], 0, 0);
      return d > from ? d : null;
    }
    for(let i = 0; i < 8; i++){
      const d = new Date(from.getFullYear(), from.getMonth(), from.getDate() + i, tm[0], tm[1], 0, 0);
      if(d > from && days.includes(d.getDay())) return d;
    }
    return null;
  };

  /* Turn finished one-shots off, and pin the date on one-shots that arrived without one. */
  AL.sweep = () => {
    const now = new Date(), today = ld(now);
    A.list('alm').forEach(a => {
      if(!a.on || cleanDays(a.days).length) return;
      const tm = parseTime(a.time); if(!tm) return;
      if(!a.once){ const n = AL.next(a, now); if(n) A.put('alm', a.id, Object.assign({}, a, { once: ld(n) })); return; }
      const when = new Date(+a.once.slice(0, 4), +a.once.slice(5, 7) - 1, +a.once.slice(8, 10), tm[0], tm[1]);
      if(a.once < today || (a.once === today && now - when > 120000)) A.put('alm', a.id, Object.assign({}, a, { on: false }));
    });
  };

  AL.entries = () => {
    const out = [];
    A.list('alm').forEach(a => {
      if(!a.on) return;
      const tm = parseTime(a.time); if(!tm) return;
      const title = clip(a.label, 60) || 'Alarm', body = A.ftime(a.time), days = cleanDays(a.days);
      if(days.length) days.forEach(d => out.push({ id: nid(a.id + ':' + d), title, body, on:{ weekday: d + 1, hour: tm[0], minute: tm[1] }, aid: a.id }));
      else { const n = AL.next(a); if(n) out.push({ id: nid(a.id + ':once'), title, body, at: n.getTime(), aid: a.id }); }
    });
    return out;
  };
  AL.signature = ents => String(h32(JSON.stringify((ents || AL.entries()).map(e => [e.id, e.title, e.body, e.on || e.at]))));

  async function ensureChannel(ln){
    try{ await ln.createChannel({ id: CH, name:'Alarms', description:'Almanac alarms', importance: 5, visibility: 1, vibration: true, lights: true }); }catch(e){}
  }
  AL.checkPerm = async () => {
    const ln = LN(); if(!ln) return AL.perm;
    try{ const p = await ln.checkPermissions(); AL.perm.display = p.display || 'unknown'; }catch(e){}
    try{ if(ln.checkExactNotificationSetting){ const p = await ln.checkExactNotificationSetting(); AL.perm.exact = p.exact_alarm || 'unknown'; } else AL.perm.exact = 'granted'; }catch(e){ AL.perm.exact = 'granted'; }
    if(modOpen('alm')) A.renderMod();
    return AL.perm;
  };
  AL.askPerm = async () => {
    const ln = LN(); if(!ln) return;
    await ensureChannel(ln);
    try{ const p = await ln.requestPermissions(); AL.perm.display = p.display || AL.perm.display; }catch(e){}
    try{
      if(ln.checkExactNotificationSetting){
        const p = await ln.checkExactNotificationSetting();
        if(p.exact_alarm === 'denied' && ln.changeExactNotificationSetting){ A.toast('Allow "Alarms & reminders" for Almanac so alarms ring on time'); await ln.changeExactNotificationSetting(); }
      }
    }catch(e){}
    await AL.checkPerm(); AL.resched(true);
  };

  AL.resched = async force => {
    const ln = LN(); if(!ln) return;
    if(AL.busy){ AL.again = true; return; }
    AL.busy = true;
    try{
      AL.sweep();
      const ents = AL.entries(), sig = AL.signature(ents);
      if(!force && sig === lsGet(SIG_KEY)) return;
      await ensureChannel(ln);
      let ids = []; try{ ids = JSON.parse(lsGet(IDS_KEY) || '[]') || []; }catch(e){}
      try{ const p = await ln.getPending(); (p.notifications || []).forEach(n => { if(n.extra && n.extra.src === 'almanac-alarm' && !ids.includes(n.id)) ids.push(n.id); }); }catch(e){}
      if(ids.length){ try{ await ln.cancel({ notifications: ids.map(id => ({ id })) }); }catch(e){} }
      if(ents.length){
        if(AL.perm.display === 'unknown') await AL.checkPerm();
        if(AL.perm.display !== 'granted'){ lsSet(IDS_KEY, '[]'); return; }
        await ln.schedule({ notifications: ents.map(e => ({
          id: e.id, title: e.title, body: e.body, channelId: CH, actionTypeId:'ALARM', autoCancel: true,
          schedule: e.on ? { on: e.on, allowWhileIdle: true } : { at: new Date(e.at), allowWhileIdle: true },
          extra:{ src:'almanac-alarm', aid: e.aid }
        })) });
      }
      lsSet(IDS_KEY, JSON.stringify(ents.map(e => e.id))); lsSet(SIG_KEY, sig);
    }catch(e){ console.error('alarm schedule', e); }
    finally{ AL.busy = false; if(AL.again){ AL.again = false; setTimeout(() => AL.resched(), 0); } }
  };

  async function nativeInit(){
    const ln = LN(); if(!ln || AL.inited) return; AL.inited = true;
    await ensureChannel(ln);
    try{ await ln.registerActionTypes({ types:[{ id:'ALARM', actions:[{ id:'snooze', title:'Snooze ' + SNOOZE_MIN + ' min' }, { id:'dismiss', title:'Dismiss' }] }] }); }catch(e){}
    const info = n => { const x = (n && n.extra) || {}; return (x.src === 'almanac-alarm' || x.src === 'almanac-snooze') ? { aid: x.aid, label: n.title || 'Alarm', time: n.body || '' } : null; };
    try{
      ln.addListener('localNotificationActionPerformed', ev => {
        const i = info(ev && ev.notification); if(!i) return;
        if(ev.actionId === 'snooze') AL.snoozeFor(i);
        else if(ev.actionId === 'dismiss') AL.finish(i.aid);
        else AL.ring(i);
      });
      ln.addListener('localNotificationReceived', ev => { const i = info(ev); if(i) AL.ring(i); });
    }catch(e){}
    await AL.checkPerm();
  }

  /* ---------- ring overlay (foreground / web) ---------- */
  function beep(){
    try{
      const C = root.AudioContext || root.webkitAudioContext; if(!C) return;
      AL.ctx = AL.ctx || new C(); const c = AL.ctx; if(c.state === 'suspended') c.resume();
      [0, 0.28, 0.56].forEach(dt => {
        const o = c.createOscillator(), g = c.createGain(); o.type = 'sine'; o.frequency.value = 880;
        g.gain.setValueAtTime(0.0001, c.currentTime + dt); g.gain.exponentialRampToValueAtTime(0.3, c.currentTime + dt + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, c.currentTime + dt + 0.2);
        o.connect(g); g.connect(c.destination); o.start(c.currentTime + dt); o.stop(c.currentTime + dt + 0.22);
      });
    }catch(e){}
    try{ navigator.vibrate && navigator.vibrate([300, 150, 300]); }catch(e){}
  }
  AL.ring = i => {
    AL.ringing = i;
    let el = $('mRing');
    if(!el){ el = document.createElement('div'); el.id = 'mRing'; el.className = 'm-ring'; el.setAttribute('role', 'alertdialog'); el.setAttribute('aria-live', 'assertive'); document.body.appendChild(el); }
    const a = A.get('alm', i.aid);
    el.innerHTML = '<div class="pulse">' + A.icon('alarm', true) + '</div><div class="t">' + E(a ? A.ftime(a.time) : (i.time || '')) + '</div><div class="l">' + E(i.label || (a && a.label) || 'Alarm') + '</div>' +
      '<div class="btns"><button class="btn btn-ghost" onclick="AL.snoozeNow()">Snooze ' + SNOOZE_MIN + ' min</button><button class="btn btn-primary" onclick="AL.dismiss()">Dismiss</button></div>';
    el.classList.add('show');
    clearInterval(AL.beepT); beep(); AL.beepT = setInterval(beep, 1500);
  };
  AL.stopRing = () => { clearInterval(AL.beepT); AL.beepT = null; const el = $('mRing'); if(el) el.classList.remove('show'); };
  AL.finish = aid => { const a = aid && A.get('alm', aid); if(a && !cleanDays(a.days).length && a.on){ A.put('alm', aid, Object.assign({}, a, { on: false })); if(modOpen('alm')) A.renderMod(); } };
  AL.dismiss = () => { const i = AL.ringing; AL.ringing = null; AL.stopRing(); if(i) AL.finish(i.aid); };
  AL.snoozeFor = async i => {
    const at = Date.now() + SNOOZE_MIN * 60000;
    AL.finish(i.aid);
    const ln = LN();
    if(ln){
      try{ await ln.schedule({ notifications:[{ id: nid('snooze:' + i.aid + ':' + (at % 1e9)), title: i.label || 'Alarm', body:'Snoozed', channelId: CH, actionTypeId:'ALARM', autoCancel: true,
        schedule:{ at: new Date(at), allowWhileIdle: true }, extra:{ src:'almanac-snooze', aid: i.aid } }] }); }catch(e){ console.error(e); }
    }else{
      AL.snoozes.push({ aid: i.aid, label: i.label, at }); lsSet(SNZ_KEY, JSON.stringify(AL.snoozes));
    }
    A.toast('Snoozed for ' + SNOOZE_MIN + ' minutes');
  };
  AL.snoozeNow = () => { const i = AL.ringing; AL.ringing = null; AL.stopRing(); if(i) AL.snoozeFor(i); };

  /* One pass every 20s: web ring + sweep. On native the OS rings, so only the sweep runs. */
  AL.tick = () => {
    AL.sweep();
    if(native()) return;
    const now = new Date(), today = ld(now);
    A.list('alm').forEach(a => {
      if(!a.on) return;
      const tm = parseTime(a.time); if(!tm) return;
      const days = cleanDays(a.days), t0 = new Date(now.getFullYear(), now.getMonth(), now.getDate(), tm[0], tm[1], 0, 0);
      if(days.length ? !days.includes(t0.getDay()) : a.once !== today) return;
      const age = now - t0; if(age < 0 || age > 120000) return;
      const key = a.id + ':' + today + ':' + a.time; if(AL.rung[key]) return;
      AL.rung[key] = 1; const ks = Object.keys(AL.rung); if(ks.length > 60) ks.slice(0, ks.length - 60).forEach(k => delete AL.rung[k]);
      lsSet(RUNG_KEY, JSON.stringify(AL.rung));
      AL.ring({ aid: a.id, label: a.label || 'Alarm', time: A.ftime(a.time) });
    });
    const due = AL.snoozes.filter(s => s.at <= Date.now());
    if(due.length){ AL.snoozes = AL.snoozes.filter(s => s.at > Date.now()); lsSet(SNZ_KEY, JSON.stringify(AL.snoozes)); AL.ring({ aid: due[0].aid, label: due[0].label || 'Alarm' }); }
  };

  /* ---------- alarm UI ---------- */
  const daysText = a => {
    const d = cleanDays(a.days).join('');
    if(!d) return 'Once'; if(d === '0123456') return 'Every day'; if(d === '12345') return 'Weekdays'; if(d === '06') return 'Weekends';
    return cleanDays(a.days).map(x => DAYN[x]).join(' ');
  };
  function alRender(el){
    const list = A.list('alm').sort((a, b) => String(a.time).localeCompare(String(b.time)));
    let h = A.head('Alarms', { add:'AL.edit(null)', addLabel:'Add alarm', sub: native() ? 'Rings even when Almanac is closed.' : 'These ring while Almanac is open. The Android app rings in the background.' });
    if(native()){
      if(AL.perm.display === 'denied' || AL.perm.display === 'prompt' || AL.perm.display === 'prompt-with-rationale')
        h += '<div class="m-note">Alarms need notification permission. <button class="btn btn-primary" style="margin-top:10px" onclick="AL.askPerm()">Allow alarms</button></div>';
      else if(AL.perm.exact === 'denied')
        h += '<div class="m-note">Android may delay alarms until you allow &ldquo;Alarms &amp; reminders&rdquo;. <button class="btn btn-primary" style="margin-top:10px" onclick="AL.askPerm()">Open setting</button></div>';
    }
    h += '<div class="card" style="padding:0;overflow:hidden">' + (list.map(a =>
      '<div class="m-alarm ' + (a.on ? '' : 'off') + '"><button class="grow" style="text-align:left" onclick="AL.edit(\'' + J(a.id) + '\')"><div class="tm">' + E(A.ftime(a.time)) + '</div>' +
      '<div class="lbl">' + E(a.label || 'Alarm') + ' &middot; ' + E(daysText(a)) + '</div></button>' +
      '<button class="m-switch ' + (a.on ? 'on' : '') + '" role="switch" aria-checked="' + (a.on ? 'true' : 'false') + '" aria-label="Alarm on" onclick="AL.toggle(\'' + J(a.id) + '\')"></button></div>'
    ).join('') || '<div class="empty">No alarms yet.</div>') + '</div>';
    el.innerHTML = h;
    if(native() && AL.perm.display === 'unknown') AL.checkPerm();
  }
  AL.edit = id => {
    const a = id ? A.get('alm', id) : { label:'', time:'07:00', days:[], on: true };
    if(!a) return; const sel = cleanDays(a.days);
    openSheet('<h3>' + (id ? 'Edit alarm' : 'New alarm') + '</h3>' +
      '<input id="alTime" class="m-time" type="time" value="' + E(a.time || '07:00') + '" aria-label="Time">' +
      '<div class="m-days" id="alDays">' + DAYL.map((l, i) => '<button type="button" class="' + (sel.includes(i) ? 'sel' : '') + '" data-d="' + i + '" aria-label="' + DAYN[i] + '" onclick="AL.day(this)">' + l + '</button>').join('') + '</div>' +
      '<div class="chip-select" style="margin-bottom:12px"><button class="chip-opt" onclick="AL.preset(\'once\')">Once</button><button class="chip-opt" onclick="AL.preset(\'wk\')">Weekdays</button><button class="chip-opt" onclick="AL.preset(\'all\')">Every day</button></div>' +
      '<div class="field"><label for="alLabel">Label</label><input id="alLabel" maxlength="60" placeholder="Wake up" value="' + E(a.label) + '"></div>' +
      '<div class="sheet-actions">' + (id ? '<button class="btn btn-ghost btn-danger" onclick="AL.del(\'' + J(id) + '\')">Delete</button>' : '<button class="btn btn-ghost" onclick="closeSheet()">Cancel</button>') +
      '<button class="btn btn-primary" onclick="AL.save(' + (id ? "'" + J(id) + "'" : 'null') + ')">Save</button></div>');
  };
  AL.day = b => b.classList.toggle('sel');
  AL.preset = p => {
    const want = p === 'wk' ? [1, 2, 3, 4, 5] : p === 'all' ? [0, 1, 2, 3, 4, 5, 6] : [];
    document.querySelectorAll('#alDays button').forEach(b => b.classList.toggle('sel', want.includes(+b.dataset.d)));
  };
  AL.save = id => {
    const time = val('alTime'); if(!parseTime(time)){ A.toast('Pick a time'); return; }
    const days = Array.from(document.querySelectorAll('#alDays button.sel')).map(b => +b.dataset.d);
    const old = id ? A.get('alm', id) : null, rec = { label: clip(val('alLabel'), 60), time, days, on: true };
    if(!days.length){ const n = AL.next({ time, days: [] }); if(n) rec.once = ld(n); }
    if(old && old.on === false && false) rec.on = false;
    A.put('alm', id || A.uid(), rec); closeSheet(); A.renderMod();
    if(native()) AL.askPermIfNeeded();
    AL.resched();
  };
  AL.askPermIfNeeded = async () => { await AL.checkPerm(); if(AL.perm.display !== 'granted' || AL.perm.exact === 'denied') AL.askPerm(); };
  AL.del = id => { A.del('alm', id); closeSheet(); A.renderMod(); AL.resched(); };
  AL.toggle = id => {
    const a = A.get('alm', id); if(!a) return;
    const rec = Object.assign({}, a, { on: !a.on });
    if(rec.on && !cleanDays(rec.days).length){ const n = AL.next({ time: rec.time, days: [] }); rec.once = n ? ld(n) : ''; if(!rec.once) delete rec.once; }
    A.put('alm', id, rec); A.renderMod(); if(rec.on && native()) AL.askPermIfNeeded(); AL.resched();
  };
  AL.nextAny = () => {
    let best = null, ba = null;
    A.list('alm').forEach(a => { if(!a.on) return; const n = AL.next(a); if(n && (!best || n < best)){ best = n; ba = a; } });
    return best ? { at: best, a: ba } : null;
  };
  A.reg({ id:'alm', title:'Alarms', icon:'alarm', desc:'Wake-ups & reminders', group:'live',
    badge(){ const n = AL.nextAny(); return n ? 'Next ' + A.ftime(n.a.time) : 'Wake-ups & reminders'; },
    chip(){
      const n = AL.nextAny(); if(!n) return null;
      const sameDay = ld(n.at) === ld(new Date());
      return { k:'Next alarm', v: A.ftime(n.a.time) + (sameDay ? '' : ' ' + DAYN[n.at.getDay()]) };
    },
    render: alRender });

  A.on('saved', (() => { let t; return () => { clearTimeout(t); t = setTimeout(() => AL.resched(), 800); }; })());
  A.on('afterSync', kinds => { if(!kinds || kinds.has && kinds.has('alm') || Array.isArray(kinds) && kinds.includes('alm')) AL.resched(); });
  A.on('boot', () => { nativeInit().then(() => AL.resched()); AL.tick(); setInterval(AL.tick, 20000); });
  document.addEventListener('visibilitychange', () => { if(!document.hidden){ AL.tick(); if(native()) AL.checkPerm().then(() => AL.resched()); } });

  /* ============================================================ LIVE LINK (WebSocket) ============================================================ */
  const RT = root.RT = { ws:null, state:'off', tries:0, dead:false, retryT:null, pingT:null, lastRx:0, authT:null, role:null, id:null, clips:[] };
  RT.url = () => { const c = cfg(); return (c && c.url && c.token) ? c.url.replace(/^http/i, 'ws') + '/api/almanac/ws' : null; };
  RT.paint = () => {
    const txt = RT.state === 'on' ? 'Live' : RT.state === 'connecting' ? 'Connecting' : 'Offline', cls = RT.state === 'on' ? 'on' : RT.state === 'connecting' ? 'wait' : '';
    document.querySelectorAll('.js-live').forEach(el => { el.className = 'm-live js-live ' + cls; el.innerHTML = '<i></i>' + txt; });
  };
  const setState = s => { RT.state = s; RT.paint(); A.fire('wsState', s); };
  RT.live = () => '<span class="m-live js-live ' + (RT.state === 'on' ? 'on' : RT.state === 'connecting' ? 'wait' : '') + '"><i></i>' + (RT.state === 'on' ? 'Live' : RT.state === 'connecting' ? 'Connecting' : 'Offline') + '</span>';
  RT.send = o => { if(RT.ws && RT.state === 'on'){ try{ RT.ws.send(JSON.stringify(o)); return true; }catch(e){} } return false; };
  RT.connect = () => {
    if(RT.ws || RT.dead || document.hidden) return;
    const u = RT.url(); if(!u || !root.SYNC_MODE) return;
    let ws; try{ ws = new WebSocket(u); }catch(e){ RT.retry(); return; }
    RT.ws = ws; setState('connecting');
    ws.onopen = () => { try{ ws.send(JSON.stringify({ t:'auth', token: cfg().token })); }catch(e){} RT.authT = setTimeout(() => { try{ ws.close(); }catch(e){} }, 10000); };
    ws.onmessage = ev => { let m; try{ m = JSON.parse(ev.data); }catch(e){ return; } RT.lastRx = Date.now(); RT.onMsg(m); };
    ws.onerror = () => {};
    ws.onclose = ev => {
      if(RT.ws !== ws) return;
      clearTimeout(RT.authT); clearInterval(RT.pingT); RT.ws = null; setState('off');
      if(ev.code === 4401){ RT.dead = true; return; }
      if(ev.code === 4403){ RT.dead = true; A.toast('Your family access was removed'); return; }
      RT.retry(ev.code === 1013 || ev.code === 4429 ? 30000 : 0);
    };
  };
  RT.retry = min => {
    clearTimeout(RT.retryT);
    const d = Math.max(min || 0, Math.min(1000 * Math.pow(2, RT.tries++), 30000)) * (0.8 + Math.random() * 0.4);
    RT.retryT = setTimeout(RT.connect, d);
  };
  RT.close = () => { clearTimeout(RT.retryT); clearInterval(RT.pingT); clearTimeout(RT.authT); const w = RT.ws; RT.ws = null; if(w){ try{ w.onclose = null; w.close(); }catch(e){} } setState('off'); };
  RT.restart = () => { RT.close(); RT.dead = false; RT.tries = 0; RT.connect(); };
  RT.onMsg = m => {
    switch(m.t){
      case 'hello':
        clearTimeout(RT.authT); RT.tries = 0; RT.role = m.role || null; RT.id = m.id || null; setState('on');
        clearInterval(RT.pingT); RT.pingT = setInterval(() => { if(Date.now() - RT.lastRx > 70000){ try{ RT.ws && RT.ws.close(); }catch(e){} } else RT.send({ t:'ping' }); }, 25000);
        if(Array.isArray(m.members)){ FM.members = m.members; FM.paint(); }
        if(Array.isArray(m.clips)) CB.set(m.clips);
        FM.pull();
        A.fire('ws', m);
        break;
      case 'clip': CB.add(m.item, true); break;
      case 'clip_ack': CB.add(m.item, false); break;
      case 'clips': CB.set(m.items || []); break;
      case 'fam': FM.pull(); break;
      case 'err': if(m.msg) console.warn('almanac ws:', m.msg); break;
      default: A.fire('ws', m); break;   /* robot / AV box telemetry etc. (m-layla.js) */
    }
  };
  A.on('boot', () => RT.connect());
  A.on('config', () => RT.restart());
  A.on('state', () => { if(!RT.ws && !RT.dead) RT.connect(); });
  document.addEventListener('visibilitychange', () => { if(!document.hidden && !RT.ws && !RT.dead){ RT.tries = 0; RT.connect(); } });
  window.addEventListener('online', () => { if(!RT.ws && !RT.dead){ RT.tries = 0; RT.connect(); } });

  /* ============================================================ CLIPBOARD ============================================================ */
  const CB = root.CB = { items:[], loaded:false };
  CB.set = items => { CB.items = (Array.isArray(items) ? items : []).slice().sort((a, b) => b.ts - a.ts); CB.paint(); };
  CB.add = (item, incoming) => {
    if(!item || typeof item.text !== 'string') return;
    if(CB.items.some(i => i.id === item.id)) return;
    CB.items.unshift(item); CB.items.sort((a, b) => b.ts - a.ts); CB.items = CB.items.slice(0, 30); CB.paint();
    if(incoming && item.device !== devLabel){
      const t = item.text;
      A.toast('Clipboard from ' + (item.device || 'another device'), 'Copy', () => A.copyText(t));
    }
  };
  CB.paint = () => {
    const el = $('clipList'); if(el) el.innerHTML = CB.listHtml();
    const b = $('clipClear'); if(b) b.style.display = CB.items.length ? '' : 'none';
    if(view() === 'more') A.renderMore();
  };
  CB.listHtml = () => CB.items.length ? CB.items.map(i =>
    '<div class="m-item"><div class="grow"><div class="m-clip-txt">' + E(i.text) + '</div><div class="sub">' + E(i.device === devLabel ? 'this device' : (i.device || 'device')) + ' &middot; ' + E(A.ago(i.ts)) + '</div></div>' +
    '<button class="m-iconbtn" aria-label="Copy" onclick="CB.copy(\'' + J(i.id) + '\')">' + A.icon('copy') + '</button></div>').join('') : '<div class="empty">Nothing on the clipboard yet.</div>';
  CB.render = el => {
    if(A.isMember()){ el.innerHTML = A.head('Clipboard') + '<div class="m-note">The shared clipboard is private to the Almanac owner.</div>'; return; }
    if(!configured()){ el.innerHTML = A.head('Clipboard') + '<div class="m-note">Connect Almanac to your Layla server first (tap the sync dot at the top).</div>'; return; }
    el.innerHTML = A.head('Clipboard', { sub:'Copy on one device, paste on another. Kept for 24 hours and never written to disk.' }) +
      '<div style="display:flex;justify-content:space-between;align-items:center;margin:2px 2px 12px">' + RT.live() + '<span class="muted" style="font-size:12.5px">' + E(devLabel) + '</span></div>' +
      '<textarea id="clipIn" class="m-clip-in" maxlength="60000" placeholder="Type or paste something to send to your other devices"></textarea>' +
      '<div class="m-clip-actions"><button class="btn btn-ghost" onclick="CB.paste()">Paste here</button><button class="btn btn-primary" onclick="CB.send()">Send</button></div>' +
      '<div class="section-title">Recent</div><div class="card" id="clipList">' + CB.listHtml() + '</div>' +
      '<div style="text-align:center;margin-top:14px"><button class="btn btn-ghost btn-danger" id="clipClear" style="' + (CB.items.length ? '' : 'display:none') + '" onclick="CB.clear()">Clear all</button></div>';
    if(!RT.ws && !RT.dead) RT.connect();
    if(RT.state !== 'on') CB.load();
  };
  CB.load = async () => { try{ const r = await api('/clip'); if(r && Array.isArray(r.items)) CB.set(r.items); }catch(e){} };
  CB.paste = async () => {
    try{ const t = await navigator.clipboard.readText(); const f = $('clipIn'); if(f && t) f.value = t; else A.toast('Nothing to paste'); }
    catch(e){ A.toast('Allow clipboard access, or paste straight into the box'); }
  };
  CB.send = async () => {
    const f = $('clipIn'), text = f ? f.value : ''; if(!text.trim()) return;
    if(new TextEncoder().encode(text).length > 64000){ A.toast('That is too long for the clipboard'); return; }
    if(RT.send({ t:'clip', text, device: devLabel })){ if(f) f.value = ''; A.toast('Sent'); return; }
    try{ const r = await api('/clip', { method:'POST', body:{ text, device: devLabel } }); if(r && r.item) CB.add(r.item, false); if(f) f.value = ''; A.toast('Sent'); }
    catch(e){ A.toast(errMsg(e)); }
  };
  CB.copy = id => { const i = CB.items.find(x => x.id === id); if(!i) return; A.copyText(i.text).then(() => A.toast('Copied')); };
  CB.clear = () => A.ask('Clear clipboard?', 'This removes everything from the shared clipboard on all devices.', 'Clear', async () => {
    try{ await api('/clip/clear', { method:'POST', body:{} }); CB.set([]); }catch(e){ A.toast(errMsg(e)); }
  }, true);
  A.reg({ id:'clip', title:'Clipboard', icon:'clip', desc:'Across your devices', group:'live', owner:true,
    badge(){ return RT.state === 'on' ? 'Live' : 'Across your devices'; }, render: CB.render });

  /* ============================================================ FAMILY CONNECT ============================================================ */
  const FM = root.FM = { members:[], me:null, draft:{ status:'', note:'' } };
  const STAT = [['home', 'Home'], ['away', 'Away'], ['busy', 'Busy'], ['sleeping', 'Sleeping']];
  try{ FM.me = JSON.parse(lsGet('almanac_fam_me') || 'null'); }catch(e){ FM.me = null; }
  A.famMe = () => FM.me || (root.SYNC_MODE === 'owner' ? { id:'owner', name: lsGet('almanac_owner_name') || 'Owner', role:'owner' } : null);

  FM.pull = (() => { let t = null; return () => { clearTimeout(t); t = setTimeout(() => { if(typeof syncPullState === 'function') syncPullState('fam'); }, 250); }; })();
  FM.paint = () => {
    if(modOpen('fam') && !document.querySelector('#sheet.show, #overlay.show') && !(document.activeElement && document.activeElement.id === 'fmNote')) A.renderMod();
    if(view() === 'home' && typeof renderHome === 'function') renderHome();
  };
  A.on('state', (sp, resp) => {
    if(sp !== 'fam' || !resp) return;
    if(Array.isArray(resp.members)) FM.members = resp.members;
    if(resp.me){ FM.me = resp.me; lsSet('almanac_fam_me', JSON.stringify(resp.me)); if(resp.me.id === 'owner' && resp.me.name) lsSet('almanac_owner_name', resp.me.name); }
    FM.paint();
  });

  const initial = n => (String(n || '?').trim()[0] || '?').toUpperCase();
  const mine = m => FM.me && FM.me.id === m.id;
  const myMember = () => FM.members.find(mine) || null;
  function fmRender(el){
    if(!configured()){ el.innerHTML = A.head('Family') + '<div class="m-note">Connect Almanac to your Layla server first (tap the sync dot at the top).</div>'; return; }
    const owner = !A.isMember(), me = myMember();
    if(!FM.draft.status) FM.draft.status = (me && me.status && me.status !== 'offline') ? me.status : 'home';
    if(FM.draft.note === '' && me && me.note) FM.draft.note = me.note;
    const today = ld(new Date()), evs = A.list('fev').sort((a, b) => (String(a.date) + String(a.time || '')).localeCompare(String(b.date) + String(b.time || '')));
    const up = evs.filter(e => e.date >= today), past = evs.filter(e => e.date < today).reverse().slice(0, 5);
    const nShop = A.list('fshop').filter(i => !i.done).length;
    let h = A.head('Family', { add:'FM.editEv(null)', addLabel:'Add event', sub:'A private space for the people at home.' }) +
      '<div style="margin:2px 2px 12px">' + RT.live() + '</div>' +
      '<div class="card" style="padding:4px 16px">' + (FM.members.map(m =>
        '<div class="m-item"><span class="m-av ' + (m.online ? 'on' : '') + '">' + E(initial(m.name)) + '</span><div class="grow"><b>' + E(m.name) + (mine(m) ? ' <span class="m-badge grey">You</span>' : '') + '</b>' +
        '<div class="sub">' + E(m.role) + (m.note ? ' &middot; ' + E(m.note) : '') + (!m.online && m.seen ? ' &middot; seen ' + E(A.ago(m.seen)) : '') + '</div></div>' +
        '<span class="m-st ' + E(String(m.status).replace(/[^a-z]/g, '')) + '">' + E(m.status === 'offline' ? 'Offline' : (STAT.find(s => s[0] === m.status) || [0, m.status])[1]) + '</span>' +
        (owner && m.id !== 'owner' ? '<button class="row-x" aria-label="Remove ' + E(m.name) + '" onclick="FM.revokeAsk(\'' + J(m.id) + '\')">&#10005;</button>' : '') + '</div>').join('') || '<div class="empty">Syncing the family list&hellip;</div>') + '</div>' +
      '<div class="section-title">My status</div><div class="card" style="padding:14px 16px"><div class="chip-select" id="fmStat" style="margin-bottom:10px">' +
      STAT.map(s => '<button class="chip-opt ' + (FM.draft.status === s[0] ? 'sel' : '') + '" data-s="' + s[0] + '" onclick="FM.pick(\'' + s[0] + '\')">' + s[1] + '</button>').join('') + '</div>' +
      '<div class="field" style="margin-bottom:' + (owner ? '10' : '12') + 'px"><label for="fmNote">Note (optional)</label><input id="fmNote" maxlength="60" placeholder="Back by 6" value="' + E(FM.draft.note) + '" oninput="FM.draft.note=this.value"></div>' +
      (owner ? '<div class="field" style="margin-bottom:12px"><label for="fmName">Your name</label><input id="fmName" maxlength="30" placeholder="Name the family sees" value="' + E((me && me.name && me.name !== 'Owner') ? me.name : (lsGet('almanac_owner_name') || '')) + '"></div>' : '') +
      '<button class="btn btn-primary" style="width:100%" onclick="FM.share()">Update status</button></div>' +
      '<button class="m-item card" style="margin-top:14px;width:100%;text-align:left" onclick="FM.openShop()"><span class="m-ic" style="margin-right:12px">' + A.icon('cart') + '</span><div class="grow"><b>Shared shopping</b><div class="sub">' + (nShop ? nShop + ' to buy' : 'Nothing to buy') + '</div></div></button>' +
      '<div class="section-title">Coming up</div><div class="card">' + (up.map(evRow).join('') || '<div class="empty">No family events yet.</div>') + '</div>' +
      (past.length ? '<div class="section-title">Earlier</div><div class="card">' + past.map(evRow).join('') + '</div>' : '');
    if(owner) h += '<div style="text-align:center;margin-top:18px"><button class="btn btn-ghost" onclick="FM.addMember()">Add a family member</button></div>';
    el.innerHTML = h;
  }
  const evRow = e => '<button class="m-item" onclick="FM.editEv(\'' + J(e.id) + '\')"><div class="grow"><b>' + E(e.title) + '</b><div class="sub">' + E(A.fdate(e.date)) + (e.time ? ' &middot; ' + E(A.ftime(e.time)) : '') +
    (e.by ? ' &middot; ' + E(e.by) : '') + (e.note ? ' &middot; ' + E(e.note) : '') + '</div></div></button>';

  FM.pick = s => { FM.draft.status = s; document.querySelectorAll('#fmStat .chip-opt').forEach(b => b.classList.toggle('sel', b.dataset.s === s)); };
  FM.share = async () => {
    const body = { status: FM.draft.status || 'home', note: clip(FM.draft.note, 60) };
    if(!A.isMember()){ const n = clip(val('fmName'), 30); if(n) body.name = n; }
    try{ const r = await api('/family/presence', { method:'POST', body }); if(r && Array.isArray(r.members)) FM.members = r.members; if(body.name) lsSet('almanac_owner_name', body.name); A.toast('Status updated'); FM.pull(); FM.paint(); }
    catch(e){ A.toast(errMsg(e)); }
  };
  FM.openShop = () => { try{ if(root.SH && !A.isMember()) root.SH.tab('family'); }catch(e){} A.open('shop'); };

  FM.editEv = id => {
    const e = id ? A.get('fev', id) : { title:'', date: ld(new Date()), time:'', note:'' };
    if(!e) return;
    openSheet('<h3>' + (id ? 'Edit event' : 'New family event') + '</h3>' +
      '<div class="field"><label for="feTitle">What</label><input id="feTitle" maxlength="80" value="' + E(e.title) + '"></div>' +
      '<div class="field-row"><div class="field"><label for="feDate">Date</label><input id="feDate" type="date" value="' + E(e.date) + '"></div>' +
      '<div class="field"><label for="feTime">Time (optional)</label><input id="feTime" type="time" value="' + E(e.time) + '"></div></div>' +
      '<div class="field"><label for="feNote">Note (optional)</label><input id="feNote" maxlength="120" value="' + E(e.note) + '"></div>' +
      '<div class="sheet-actions">' + (id ? '<button class="btn btn-ghost btn-danger" onclick="FM.delEv(\'' + J(id) + '\')">Delete</button>' : '<button class="btn btn-ghost" onclick="closeSheet()">Cancel</button>') +
      '<button class="btn btn-primary" onclick="FM.saveEv(' + (id ? "'" + J(id) + "'" : 'null') + ')">Save</button></div>');
  };
  FM.saveEv = id => {
    const title = clip(val('feTitle'), 80), date = val('feDate'), time = val('feTime');
    if(!title){ A.toast('Give the event a name'); return; }
    if(!/^\d{4}-\d{2}-\d{2}$/.test(date)){ A.toast('Pick a date'); return; }
    const old = id ? A.get('fev', id) : null, me = A.famMe();
    A.put('fev', id || A.uid(), { title, date, time: /^\d{2}:\d{2}$/.test(time) ? time : '', note: clip(val('feNote'), 120), by: old && old.by ? old.by : clip(me && me.name || '', 30) });
    closeSheet(); A.renderMod();
  };
  FM.delEv = id => { A.del('fev', id); closeSheet(); A.renderMod(); };

  FM.addMember = () => openSheet('<h3>Add a family member</h3>' +
    '<p class="muted" style="font-size:13.5px;line-height:1.5;margin:0 0 12px">They get their own access key. They can see shared shopping, events and who is home, and nothing else.</p>' +
    '<div class="field"><label for="fmaName">Name</label><input id="fmaName" maxlength="30" placeholder="Their name"></div>' +
    '<div class="field"><label for="fmaRole">Role</label><input id="fmaRole" maxlength="20" placeholder="Wife, Son, Parent&hellip;"></div>' +
    '<div class="chip-select" style="margin-bottom:12px">' + ['Wife', 'Husband', 'Son', 'Daughter', 'Parent'].map(r => '<button class="chip-opt" onclick="document.getElementById(\'fmaRole\').value=\'' + r + '\'">' + r + '</button>').join('') + '</div>' +
    '<div class="sheet-actions"><button class="btn btn-ghost" onclick="closeSheet()">Cancel</button><button class="btn btn-primary" onclick="FM.createMember()">Create key</button></div>');
  FM.createMember = async () => {
    const name = clip(val('fmaName'), 30), role = clip(val('fmaRole'), 20) || 'Member';
    if(!name){ A.toast('Enter a name'); return; }
    if(!/^[A-Za-z][A-Za-z ]{0,19}$/.test(role)){ A.toast('Role can only use letters'); return; }
    try{
      const r = await api('/family/members', { method:'POST', body:{ name, role } });
      const c = cfg();
      openSheet('<h3>Key for ' + E(name) + '</h3><p class="muted" style="font-size:13.5px;line-height:1.5;margin:0">Shown once. On their phone, open Almanac, tap the sync dot at the top and enter:</p>' +
        '<div class="muted" style="font-size:12.5px;margin-top:10px">Server</div><div class="m-token">' + E(c && c.url || '') + '</div>' +
        '<div class="muted" style="font-size:12.5px">Access key</div><div class="m-token" id="fmTok">' + E(r.token) + '</div>' +
        '<div class="sheet-actions"><button class="btn btn-ghost" onclick="FM.copyTok()">Copy key</button><button class="btn btn-primary" onclick="closeSheet()">Done</button></div>');
      if(Array.isArray(r.members)) FM.members = r.members; FM.pull();
    }catch(e){ A.toast(errMsg(e)); }
  };
  FM.copyTok = () => { const t = $('fmTok'); if(t) A.copyText(t.textContent).then(() => A.toast('Copied')); };
  FM.revokeAsk = id => { const m = FM.members.find(x => x.id === id); A.ask('Remove ' + (m ? m.name : 'member') + '?', 'Their key stops working straight away. Shared items stay.', 'Remove', async () => {
    try{ await api('/family/members/revoke', { method:'POST', body:{ id } }); A.toast('Removed'); FM.pull(); }catch(e){ A.toast(errMsg(e)); }
  }, true); };

  A.reg({ id:'fam', title:'Family', icon:'family', desc:'Shared space at home', group:'live', member:true,
    badge(){ const n = FM.members.filter(m => m.id !== (FM.me && FM.me.id) && m.status === 'home').length; return n ? n + ' home' : 'Shared space at home'; },
    chip(){
      const today = ld(new Date()), soon = ld(new Date(Date.now() + 2 * 86400000));
      const ev = A.list('fev').filter(e => e.date >= today && e.date <= soon).sort((a, b) => String(a.date).localeCompare(String(b.date)))[0];
      if(ev) return { k:'Family', v: ev.title + ' · ' + A.fdate(ev.date) };
      const n = FM.members.filter(m => !mine(m) && m.status === 'home').length;
      return FM.members.length > 1 ? { k:'Family', v: n + ' home' } : null;
    }, render: fmRender });
})(typeof window !== 'undefined' ? window : globalThis);
