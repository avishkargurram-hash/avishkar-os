/* Layla modules: the GR robot (two-stick drive) and the AV sensor box (room readings + IR remote).
   Owner only (no `member` flag, so family members never see these). Everything goes through the Layla server
   (/api/almanac/robot|avbox|body), which owns the safety rules; this page never talks to MQTT directly.
   Loaded after m-infra.js: uses RT (live WebSocket) and the 'ws' / 'wsState' hooks it fires. */
(function(root){
  'use strict';
  const A = root.ALM;
  const $ = A.$, E = A.E, J = A.J;
  const RT = () => root.RT;
  const cfg = () => (typeof syncCfg === 'function') ? syncCfg() : null;
  const configured = () => (typeof syncConfigured === 'function') ? !!syncConfigured() : false;
  const view = () => (typeof currentView !== 'undefined') ? currentView : '';
  const modOpen = id => view() === 'mod' && A.cur === id;
  async function api(path, opts){
    const c = cfg(); if(!c || !c.token) throw new Error('Connect to your Layla server first');
    const o = Object.assign({}, opts);
    if(o.body && typeof o.body !== 'string') o.body = JSON.stringify(o.body);
    if(o.body) o.headers = Object.assign({ 'Content-Type':'application/json' }, o.headers);
    return syncFetch(c, path, o);
  }
  const errMsg = e => (e && e.message) || 'Something went wrong';
  const lsGet = k => { try{ return localStorage.getItem(k); }catch(e){ return null; } };
  const lsSet = (k, v) => { try{ localStorage.setItem(k, v); }catch(e){} };

  const L = root.LAYLA = { body:null, at:0 };

  /* ---------- shared telemetry ---------- */
  L.set = s => {
    if(!s || typeof s !== 'object') return;
    L.body = { link: s.link, robot: s.robot || {}, avbox: s.avbox || {}, home: s.home || null, presence: s.presence || null };
    L.at = Date.now();
    if(modOpen('robot')) RB.paint();
    else if(modOpen('avbox')) AV.paint();
    else if(view() === 'more'){
      const sig = ['robot', 'avbox'].map(id => { try{ return A.mods[id].badge(); }catch(e){ return ''; } }).join('|');
      if(sig !== L.sig){ L.sig = sig; A.renderMore(); }      // telemetry is frequent; only repaint when a tile changes
    }
  };
  L.pull = async () => { try{ const r = await api('/body/state'); L.set(r); }catch(e){} };
  A.on('ws', m => {
    if(m.t === 'hello' && m.body) L.set(m.body);
    else if(m.t === 'body') L.set(m);
    else if(m.t === 'robot.err' && modOpen('robot')){ RB.flash(m.msg || 'The robot refused that'); }
  });
  A.on('wsState', s => { if(modOpen('robot')) RB.paintLink(); if(s !== 'on' && RB.driving()) RB.release(); });

  const live = () => RT() ? RT().live() : '';
  const pill = (txt, cls) => '<span class="m-badge ' + (cls || '') + '">' + E(txt) + '</span>';

  /* ======================================================= ROBOT ======================================================= */
  const RB = root.RB = { fy:0, rx:0, last:null, lastAt:0, tick:null, max:+(lsGet('gr_max2') || 170), t0:0 };
  /* Speeds are PWM 0-255. 90 is the lowest the TT motors still turn smoothly on the 7.4 V pack (owner-calibrated 2026-10-22).
     A small push stays gentle (squared curve), the speed eases in over RAMP_MS, and turning is capped lower than driving. */
  const DEAD = 0.25, MIN = 90, TICK_MS = 120, RESEND_MS = 250, RAMP_MS = 400, TURN_SHARE = 0.8;

  RB.driving = () => RB.last !== null;
  RB.flash = msg => { const el = $('grMsg'); if(el){ el.textContent = msg; el.className = 'gr-msg bad'; clearTimeout(RB.ft); RB.ft = setTimeout(() => { el.textContent = ''; el.className = 'gr-msg'; }, 3500); } };

  RB.send = (action, speed) => {
    if(RT() && RT().send({ t:'robot.drive', a:action, s:speed })) return;
    api('/robot/drive', { method:'POST', body:{ action, speed } }).catch(e => RB.flash(errMsg(e)));   // slower fallback
  };
  RB.stop = () => {
    RB.last = null;
    const viaWs = RT() && RT().send({ t:'robot.stop' });
    if(!viaWs) api('/robot/stop', { method:'POST', body:{} }).catch(() => {});
  };
  RB.release = () => { RB.fy = 0; RB.rx = 0; RB.resetKnobs(); RB.stop(); };

  RB.step = () => {
    const mf = Math.abs(RB.fy), mt = Math.abs(RB.rx);
    let action = null, mag = 0;
    if(mf > DEAD || mt > DEAD){
      if(mf >= mt){ action = RB.fy > 0 ? 'forward' : 'backward'; mag = mf; }
      else { action = RB.rx > 0 ? 'right' : 'left'; mag = mt; }
    }
    const now = Date.now();
    if(action){
      const turning = action === 'left' || action === 'right';
      const top = Math.max(MIN + 10, turning ? Math.round(RB.max * TURN_SHARE) : RB.max);
      const t = Math.min(1, Math.max(0, (mag - DEAD) / (1 - DEAD)));
      if(action !== RB.last) RB.t0 = now;
      const ramp = Math.min(1, (now - RB.t0) / RAMP_MS);
      const speed = Math.round(MIN + t * t * (top - MIN) * ramp);
      if(action !== RB.last || now - RB.lastAt >= RESEND_MS){ RB.send(action, Math.min(255, Math.max(MIN, speed))); RB.last = action; RB.lastAt = now; }
    } else if(RB.last !== null){
      RB.stop();
      setTimeout(() => { if(RB.last === null && RT()) RT().send({ t:'robot.stop' }); }, 120);   // one lost frame must not leave it running
    }
  };

  /* A stick tracks one pointer; two sticks work at the same time (multi-touch). axis: 'y' or 'x'. */
  RB.bindStick = (id, axis) => {
    const pad = $(id); if(!pad) return;
    const knob = pad.querySelector('.gr-knob');
    let pid = null;
    const move = ev => {
      const r = pad.getBoundingClientRect(), reach = r.width * 0.32;
      let dx = ev.clientX - (r.left + r.width / 2), dy = ev.clientY - (r.top + r.height / 2);
      if(axis === 'y') dx = 0; else dy = 0;
      const d = Math.hypot(dx, dy); if(d > reach){ dx *= reach / d; dy *= reach / d; }
      knob.style.transform = 'translate(' + dx + 'px,' + dy + 'px)';
      if(axis === 'y') RB.fy = -dy / reach; else RB.rx = dx / reach;
    };
    const end = ev => {
      if(ev.pointerId !== pid) return;
      pid = null; knob.style.transform = '';
      if(axis === 'y') RB.fy = 0; else RB.rx = 0;
      pad.classList.remove('on');
    };
    pad.addEventListener('pointerdown', ev => {
      if(pid !== null) return;
      pid = ev.pointerId; pad.setPointerCapture(pid); pad.classList.add('on'); move(ev); ev.preventDefault();
    });
    pad.addEventListener('pointermove', ev => { if(ev.pointerId === pid) move(ev); });
    pad.addEventListener('pointerup', end); pad.addEventListener('pointercancel', end); pad.addEventListener('lostpointercapture', end);
  };
  RB.resetKnobs = () => document.querySelectorAll('.gr-knob').forEach(k => { k.style.transform = ''; });

  RB.setMax = v => { RB.max = Math.max(MIN + 10, Math.min(255, +v || 170)); lsSet('gr_max2', String(RB.max)); const o = $('grMaxV'); if(o) o.textContent = Math.round(RB.max / 2.55) + '%'; };
  RB.flip = async (axis, value) => {
    const body = axis === 'fb' ? { invert_fb: value } : { invert_lr: value };
    try{ const r = await api('/robot/config', { method:'POST', body }); if(L.body) L.body.robot.config = r.config; RB.paint(); A.toast('Saved'); }
    catch(e){ A.toast(errMsg(e)); }
  };

  RB.paintLink = () => { const el = $('grLive'); if(el) el.innerHTML = live(); };
  RB.paint = () => {
    RB.paintLink();
    const r = (L.body && L.body.robot) || {}, link = L.body ? L.body.link : null;
    const st = $('grStatus'); if(!st) return;
    let chips = '';
    if(link === false) chips += pill('server cannot reach the robot broker', 'bad');
    else if(r.online === true) chips += pill('GR online');
    else if(r.online === false) chips += pill('GR offline', 'bad');
    else chips += pill('GR status unknown', 'grey');
    if(r.online){
      chips += pill(r.motion && r.motion !== 'stopped' ? 'moving ' + r.motion : 'standing still', 'grey');
      if(r.distance_cm != null) chips += pill(Math.round(r.distance_cm) + ' cm ahead', r.front_blocked ? 'bad' : 'grey');
      if(r.front_blocked) chips += pill('front blocked', 'bad');
      if(r.pir != null) chips += pill(r.pir ? 'motion nearby' : 'quiet', 'grey');
    }
    st.innerHTML = chips;
    const c = r.config || {};
    const fb = $('grFb'); if(fb) fb.value = c.invert_fb === true ? 'on' : c.invert_fb === false ? 'off' : 'auto';
    const lr = $('grLr'); if(lr) lr.className = 'm-switch' + (c.invert_lr ? ' on' : '');
    const eff = $('grFbEff'); if(eff) eff.textContent = 'Firmware v' + (r.fw || 1) + ' · forward/back ' + (c.invert_fb_effective ? 'swapped' : 'as wired');
  };

  RB.startTick = () => {
    clearInterval(RB.tick);
    RB.tick = setInterval(() => { if(!modOpen('robot')){ clearInterval(RB.tick); RB.tick = null; if(RB.driving()) RB.release(); return; } RB.step(); }, TICK_MS);
  };
  RB.render = el => {
    /* Background syncs re-render the open module; never rebuild the sticks under a thumb that is driving. */
    if(el.querySelector('#grPadL')){ RB.paint(); if(!RB.tick) RB.startTick(); return; }
    if(!configured()){ el.innerHTML = A.head('Layla GR') + '<div class="m-note">Connect Almanac to your Layla server first (tap the sync dot at the top).</div>'; return; }
    const fbSel = '<select id="grFb" onchange="RB.flip(\'fb\', this.value === \'auto\' ? null : this.value === \'on\')">' +
      '<option value="auto">Auto (by firmware)</option><option value="on">Swapped</option><option value="off">As wired</option></select>';
    el.innerHTML = A.head('Layla GR', { sub:'Left stick: forward and back. Right stick: turn. Let go to stop.' }) +
      '<div class="gr-top"><span id="grLive"></span><div id="grStatus" class="gr-chips"></div></div>' +
      '<div class="gr-stage">' +
        '<div class="gr-pad" id="grPadL" aria-label="Forward and back"><span class="gr-lbl t">Forward</span><span class="gr-lbl b">Back</span><span class="gr-knob"></span></div>' +
        '<div class="gr-pad" id="grPadR" aria-label="Turn"><span class="gr-lbl l">Left</span><span class="gr-lbl r">Right</span><span class="gr-knob"></span></div>' +
      '</div>' +
      '<button class="gr-stop" onclick="RB.release()">Stop</button>' +
      '<div id="grMsg" class="gr-msg" role="status"></div>' +
      '<div class="section-title">Driving</div><div class="card">' +
        '<div class="m-item"><div class="grow"><b>Top speed</b><div class="sub">How fast a full push drives</div></div><span id="grMaxV" class="gr-val"></span></div>' +
        '<div style="padding:0 16px 14px"><input id="grMax" type="range" min="100" max="255" value="' + RB.max + '" oninput="RB.setMax(this.value)" style="width:100%"></div>' +
      '</div>' +
      '<div class="section-title">Calibration</div><div class="card">' +
        '<div class="m-item"><div class="grow"><b>Forward / back</b><div class="sub" id="grFbEff"></div></div>' + fbSel + '</div>' +
        '<button class="m-item" onclick="RB.flip(\'lr\', !(L_cfg().invert_lr))"><div class="grow"><b>Swap left / right</b><div class="sub">Turn on if the robot turns the wrong way</div></div><span id="grLr" class="m-switch"></span></button>' +
      '</div>' +
      '<div class="m-note">Safety: the robot stops by itself within a second if this screen, the network or the server goes away, ' +
      'and it will not drive forward into something closer than 20 cm once the front distance sensor is fitted.</div>';
    RB.bindStick('grPadL', 'y');
    RB.bindStick('grPadR', 'x');
    RB.setMax(RB.max);
    RB.paint();
    RB.startTick();
    if(RT() && !RT().ws && !RT().dead) RT().connect();
    if(!(RT() && RT().send({ t:'body.get' }))) L.pull();
  };
  root.L_cfg = () => (L.body && L.body.robot && L.body.robot.config) || {};
  document.addEventListener('visibilitychange', () => { if(document.hidden && RB.driving()) RB.release(); });

  A.reg({ id:'robot', title:'Layla GR', icon:'robot', desc:'Drive your robot', group:'layla', render: RB.render,
    badge: () => { const r = L.body && L.body.robot; return r ? (r.online ? 'Online' : r.online === false ? 'Offline' : '') : ''; } });

  /* ======================================================= BEDROOM & APPLIANCES (AV box module) =======================================================
     Dark glass control room. Readings come from the AV sensor box; the fan, plug, lights and TV go through Layla's brain
     (layla_home) which only reports success after reading the device back. Tiles marked "Connect later" are placeholders. */
  const AV = root.AV = { busy:null, pend:{}, poll:null, dimT:{} };
  const SV = (p, cls) => '<svg class="hm-i' + (cls ? ' ' + cls : '') + '" viewBox="0 0 24 24" aria-hidden="true">' + p + '</svg>';
  const HI = {
    thermo:'<path d="M10 14.5V5a2 2 0 0 1 4 0v9.5a4 4 0 1 1-4 0z"/><path d="M12 9v7"/>',
    drop:'<path d="M12 3.5s6 6.4 6 10.5a6 6 0 0 1-12 0C6 9.9 12 3.5 12 3.5z"/>',
    sun:'<circle cx="12" cy="12" r="3.6"/><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6"/>',
    motion:'<circle cx="12" cy="7.5" r="2.2"/><path d="M8.5 20l1.8-6.5 2.7 2.2 1.5 4.3M10.3 13.5l1.2-3 3.2 1.8M5 9.5a9 9 0 0 1 0 6M19 9.5a9 9 0 0 0 0 6"/>',
    wifi:'<path d="M2.5 9a14 14 0 0 1 19 0M5.5 12.3a9.5 9.5 0 0 1 13 0M8.7 15.5a5 5 0 0 1 6.6 0"/><circle cx="12" cy="18.6" r="1.1"/>',
    clock:'<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    fan:'<circle cx="12" cy="12" r="1.8"/><path d="M12 10.2c-.6-3.2.6-6.2 3.2-6.2 2.2 0 2.6 2.8.4 4.6l-2.6 1.9M13.6 12.9c3 1.1 5 3.6 3.7 5.8-1.1 1.9-3.7.9-4.1-1.9l-.3-3.2M10.5 12.9c-2.5 2.1-5.7 2.6-7 .4-1.1-1.9 1.1-3.6 3.7-2.6l3 1.3"/>',
    lamp:'<path d="M12 3v4M6 13a6 6 0 0 1 12 0z"/><path d="M10 16a2 2 0 0 0 4 0"/>',
    bulb:'<path d="M9 18h6M10 21h4M8.5 14.5a6 6 0 1 1 7 0c-.9.7-1.5 1.7-1.5 2.5h-4c0-.8-.6-1.8-1.5-2.5z"/>',
    tube:'<rect x="9" y="3" width="6" height="15" rx="3"/><path d="M10.5 18v3M13.5 18v3"/>',
    power:'<path d="M12 3.5v8"/><path d="M7 6.5a7.5 7.5 0 1 0 10 0"/>',
    mute:'<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M15.5 9.5l5 5M20.5 9.5l-5 5"/>',
    snow:'<path d="M12 2.5v19M3.8 7.2l16.4 9.6M3.8 16.8l16.4-9.6M9.5 4.2 12 6.5l2.5-2.3M9.5 19.8 12 17.5l2.5 2.3"/>',
    bolt:'<path d="M13.5 2.5 5 13.5h6.5l-1 8 8.5-11h-6.5z"/>',
    flame:'<path d="M12 21c-4 0-6-2.7-6-5.6 0-3.6 3.3-5 3.3-9.4 2.7 1.6 4 4 3.6 6.4 1-.6 1.6-1.6 1.8-3 1.9 1.6 3.3 3.8 3.3 6C18 18.3 16 21 12 21z"/>',
    heat:'<path d="M8 4c-1 1.5 1 3 0 4.5S7 11 8 12.5M12 4c-1 1.5 1 3 0 4.5S11 11 12 12.5M16 4c-1 1.5 1 3 0 4.5S15 11 16 12.5M5 17h14"/>',
    cam:'<rect x="3" y="7" width="12.5" height="10" rx="2"/><path d="M15.5 10.5 21 7.5v9l-5.5-3"/>',
    play:'<path d="M8 5.5v13l10.5-6.5z"/>',
    pause:'<path d="M8.5 5.5v13M15.5 5.5v13"/>',
    next:'<path d="M6 5.5v13l9-6.5zM18 5.5v13"/>',
    vol:'<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M15.5 9a4.5 4.5 0 0 1 0 6M18.3 6.5a8.3 8.3 0 0 1 0 11"/>',
    remote:'<rect x="8" y="2.5" width="8" height="19" rx="3"/><circle cx="12" cy="7" r="1.4"/><path d="M10.5 12h3M10.5 15h3"/>',
    motor:'<path d="M5 15h14M7 15V10a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v5M10 8V5h4v3M3 18.5h18M12 11.5h0"/>',
    washer:'<rect x="4" y="3" width="16" height="18" rx="2.5"/><circle cx="12" cy="13" r="4.5"/><path d="M7 6.5h2M15.5 6.5h1"/>',
    refresh:'<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3M19.5 4.5v4.2h-4.2"/>',
    back:'<path d="M15 5l-7 7 7 7"/>',
    minus:'<path d="M6 12h12"/>', plus:'<path d="M12 6v12M6 12h12"/>', x:'<path d="M6 6l12 12M18 6 6 18"/>'
  };
  const icon = (n, cls) => SV(HI[n] || '', cls);

  AV.home = () => (L.body && L.body.home && L.body.home.state) || null;
  AV.light = role => { const h = AV.home(), l = h && h.lights; return l && l.ok ? (l.items || []).find(i => i.role === role) || null : null; };
  AV.toggleHtml = (on, kind, js, disabled) => '<button class="hm-tg ' + kind + (on ? ' on' : '') + '"' + (disabled ? ' disabled' : '') +
    ' role="switch" aria-checked="' + (on ? 'true' : 'false') + '" onclick="' + js + '"><i></i></button>';

  /* ---------- commands ---------- */
  AV.cmd = async (device, action, value, label) => {
    if(AV.pend[device]) return;
    AV.pend[device] = true; AV.paint();
    try{
      const r = await api('/home/control', { method:'POST', body:{ device, action, value } });
      A.toast(r.ok ? (label || 'Done') : (r.msg || 'That did not work'));
    }catch(e){ A.toast(errMsg(e)); }
    finally{ delete AV.pend[device]; AV.paint(); }
  };
  AV.fanSpeed = n => AV.cmd('fan', 'speed', n, 'Fan at speed ' + n);
  AV.fanStep = d => { const f = (AV.home() || {}).fan || {}; const s = Math.max(1, Math.min(5, (f.speed || 1) + d)); AV.fanSpeed(s); };
  AV.fanToggle = () => { const f = (AV.home() || {}).fan || {}; AV.cmd('fan', f.on ? 'off' : 'on', null, f.on ? 'Fan off' : 'Fan on'); };
  AV.lightToggle = role => { const l = AV.light(role); if(!l) return; AV.cmd('light:' + role, l.on ? 'off' : 'on', null, l.on ? 'Off' : 'On'); };
  AV.dimInput = (role, el) => { el.style.setProperty('--p', el.value + '%'); const o = $('hmPct_' + role); if(o) o.textContent = el.value + '%'; };
  AV.dimSet = (role, v) => { v = Math.max(1, Math.min(100, +v || 1)); AV.cmd('light:' + role, 'dim', v, 'Brightness ' + v + '%'); };
  AV.plugToggle = () => { const p = (AV.home() || {}).plug || {}; AV.cmd('plug', p.on ? 'off' : 'on', null, p.on ? 'Plug off' : 'Plug on'); };
  AV.tv = (action, label) => AV.cmd('tv', action, null, label);
  AV.later = name => A.toast(name + ' is not connected yet. We will connect it later.');

  /* ---------- pieces ---------- */
  AV.envHtml = () => {
    const b = (L.body && L.body.avbox) || {}, s = b.sensors || {};
    const v = (id, fmt) => { const r = s[id]; return !r ? '–' : r.v == null ? 'fault' : fmt(r.v); };
    const old = id => s[id] && s[id].age_s > 120;
    const tile = (cls, label, ic, val, id) => '<div class="hm-card hm-env-t ' + cls + (id && old(id) ? ' stale' : '') + '"><div class="hm-th"><span>' + E(label) + '</span>' + icon(ic) + '</div><b>' + E(val) + '</b></div>';
    const up = s.esp32_uptime && s.esp32_uptime.v != null ? s.esp32_uptime.v : null;
    return tile('t-teal', 'Temperature', 'thermo', v('room_temperature', x => x.toFixed(1) + '°C'), 'room_temperature') +
      tile('t-blue', 'Humidity', 'drop', v('room_humidity', x => Math.round(x) + '%'), 'room_humidity') +
      tile('t-amber', 'Light', 'sun', v('ldr_light_level', x => x.toFixed(2) + ' V'), 'ldr_light_level') +
      (s.radar_presence ? (() => {   // LD2410C radar: presence even when sitting still, plus distance
        const pr = s.radar_presence.v, mv = s.radar_moving_target && s.radar_moving_target.v, d = s.radar_detection_distance && s.radar_detection_distance.v;
        const val = pr == null ? 'fault' : !pr ? 'Empty' : mv ? 'Moving' : 'Present';
        const sub = pr && d != null && d > 0 ? '<small class="hm-sub">' + (d >= 100 ? (d / 100).toFixed(1) + ' m away' : Math.round(d) + ' cm away') + '</small>' : '';
        return '<div class="hm-card hm-env-t t-green' + (b.online === false ? ' stale' : '') + '"><div class="hm-th"><span>Presence</span>' + icon('motion') + '</div><b>' + E(val) + '</b>' + sub + '</div>';
      })() : tile('t-green', 'Motion', 'motion', v('pir_motion', x => x ? 'Moving' : 'Still'), null))   // on/off sensors publish only on change: never 'old' +
      tile('t-grey', 'Wi-Fi', 'wifi', v('esp32_wifi_signal', x => Math.round(x) + ' dBm'), 'esp32_wifi_signal') +
      tile('t-mint', 'Up for', 'clock', up == null ? '–' : up < 3600 ? Math.round(up / 60) + ' min' : up < 86400 ? (up / 3600).toFixed(1) + ' h' : Math.round(up / 86400) + ' d', 'esp32_uptime');
  };

  /* Speeds 1..5 sit on an arc from lower-left over the top to lower-right. */
  const ANG = [200, 155, 110, 65, 20];          // degrees, maths convention (0 = right, 90 = up)
  const pt = (deg, r) => { const a = deg * Math.PI / 180; return [100 + r * Math.cos(a), 100 - r * Math.sin(a)]; };
  const arc = (a0, a1, r) => { const [x0, y0] = pt(a0, r), [x1, y1] = pt(a1, r); return 'M' + x0.toFixed(1) + ' ' + y0.toFixed(1) + ' A' + r + ' ' + r + ' 0 ' + (a0 - a1 > 180 ? 1 : 0) + ' 1 ' + x1.toFixed(1) + ' ' + y1.toFixed(1); };
  AV.fanHtml = () => {
    const f = (AV.home() || {}).fan || {}, ok = f.ok, on = !!f.on, sp = f.speed || 1, busy = !!AV.pend.fan;
    const end = ANG[Math.max(0, Math.min(4, sp - 1))];
    const nums = ANG.map((a, i) => { const [x, y] = pt(a, 88); return '<button class="hm-fnum' + (on && sp === i + 1 ? ' cur' : '') + '" style="left:' + (x / 2) + '%;top:' + (y / 2) + '%" onclick="AV.fanSpeed(' + (i + 1) + ')"' + (ok && !busy ? '' : ' disabled') + '>' + (i + 1) + '</button>'; }).join('');
    return '<div class="hm-th"><span>Fan + Speed</span>' + icon('fan', 'c-cyan') + '</div>' +
      '<div class="hm-dial"><svg viewBox="0 0 200 200" aria-hidden="true"><path class="trk" d="' + arc(205, -25, 64) + '"/>' +
      (on ? '<path class="val" d="' + arc(205, end, 64) + '"/><circle class="dot" cx="' + pt(end, 64)[0].toFixed(1) + '" cy="' + pt(end, 64)[1].toFixed(1) + '" r="7"/>' : '') + '</svg>' + nums +
      '<button class="hm-fanbtn' + (on ? ' on' : '') + '" aria-label="Fan on/off" onclick="AV.fanToggle()"' + (ok && !busy ? '' : ' disabled') + '>' + icon('fan', on ? 'spin' : '') + '</button></div>' +
      '<div class="hm-fspeed">' + (!ok ? 'Fan offline' : busy ? 'Working…' : on ? 'Speed ' + sp : 'Off') + '</div>' +
      '<div class="hm-seg"><button onclick="AV.fanStep(-1)"' + (ok && !busy ? '' : ' disabled') + '>' + icon('minus') + '</button>' +
      '<button class="mid' + (on ? ' on' : '') + '" onclick="AV.fanToggle()"' + (ok && !busy ? '' : ' disabled') + '>' + icon('power') + '</button>' +
      '<button onclick="AV.fanStep(1)"' + (ok && !busy ? '' : ' disabled') + '>' + icon('plus') + '</button></div>';
  };
  AV.ceilHtml = (role, title, ic) => {
    const l = AV.light(role), busy = !!AV.pend['light:' + role], ok = l && l.available;
    const pct = l ? (l.on ? Math.max(1, l.level || 100) : (AV.lastDim && AV.lastDim[role]) || 80) : 0;
    return '<div class="hm-th"><span>' + E(title) + '</span>' + icon(ic, 'c-gold') + '</div>' +
      '<div class="hm-slide"><input type="range" min="1" max="100" value="' + pct + '" aria-label="' + E(title) + ' brightness"' +
      (ok && !busy && l.dimmable ? '' : ' disabled') + ' oninput="AV.dimInput(\'' + role + '\', this)" onchange="AV.dimSet(\'' + role + '\', this.value)" style="--p:' + pct + '%">' +
      '<span id="hmPct_' + role + '">' + (l ? pct + '%' : '–') + '</span></div>' +
      '<div class="hm-glow"><span>' + (!l ? 'Not reachable' : !l.available ? 'Offline' : busy ? 'Working…' : 'Warm Amber glow') + '</span>' +
      AV.toggleHtml(l && l.on, 'amber', 'AV.lightToggle(\'' + role + '\')', !ok || busy) + '</div>';
  };
  AV.smallHtml = (role, title, ic, kind) => {
    const l = AV.light(role), busy = !!AV.pend['light:' + role], ok = l && l.available;
    return '<div class="hm-card hm-small k-' + kind + (l && l.on ? ' lit' : '') + '"><div class="hm-sname">' + E(title) + '</div>' +
      '<div class="hm-srow">' + (kind === 'green' ? '<span class="hm-on">' + (busy ? '…' : !ok ? 'Offline' : l.on ? 'On' : 'Off') + '</span>' : icon(ic, 'big')) +
      AV.toggleHtml(l && l.on, kind, 'AV.lightToggle(\'' + role + '\')', !ok || busy) + '</div></div>';
  };
  AV.appsHtml = () => {
    const h = AV.home() || {}, p = h.plug || {}, tvBusy = !!AV.pend.tv, plugBusy = !!AV.pend.plug;
    const later = (name, cls, ic, body) => '<div class="hm-card hm-app ' + cls + ' later" onclick="AV.later(\'' + name + '\')"><div class="hm-th"><span>' + name + '</span>' + icon(ic) + '</div>' + body + '<em class="hm-later">Connect later</em></div>';
    return '<div class="hm-card hm-app a-purple"><div class="hm-th"><span>Smart TV</span>' + icon('power', 'dim') + '</div>' +
        '<div class="hm-tvrow"><button class="hm-sq glow" aria-label="TV power" onclick="AV.tv(\'power\', \'TV power\')"' + (tvBusy ? ' disabled' : '') + '>' + icon('power') + '</button>' +
        '<button class="hm-round" aria-label="Mute" onclick="AV.tv(\'mute\', \'Muted\')"' + (tvBusy ? ' disabled' : '') + '>' + icon('mute') + '</button></div>' +
        (tvBusy ? '<em class="hm-note">Talking to the TV…</em>' : '') + '</div>' +
      later('Air Conditioner', 'a-teal', 'snow', '<b class="hm-big">22°C</b><div class="hm-slide"><input type="range" min="16" max="30" value="22" disabled style="--p:43%"></div>' +
        '<div class="hm-mode"><span>Quick Mode</span><span class="seg"><i class="on">Cool</i><i>Fan</i></span></div>') +
      '<div class="hm-card hm-app a-green' + (p.on ? ' lit' : '') + '"><div class="hm-th"><span>Smart Plug</span>' + icon('bolt', 'c-green') + '</div>' +
        '<div class="hm-prow"><span class="hm-bolt">' + icon('bolt') + '</span><b>' + (!p.ok ? '–' : (p.on ? Math.round(p.power_w || 0) : 0) + 'W') + '</b>' +
        AV.toggleHtml(p.on, 'green', 'AV.plugToggle()', !p.ok || plugBusy) + '</div>' + (!p.ok && h.plug ? '<em class="hm-note">Plug unreachable</em>' : '') + '</div>' +
      later('Geyser', 'a-orange', 'flame', '<div class="hm-grow"><span class="hm-heat">' + icon('heat') + '</span><b class="hm-amber">Off</b></div>') +
      '<div class="hm-card hm-app a-teal2"><div class="hm-th"><span>AV Box</span>' + icon('cam', 'dim') + '</div>' +
        '<div class="hm-media">' + [['play', 'play', 'Play'], ['pause', 'pause', 'Paused'], ['next', 'next', 'Next']].map(m =>
          '<button aria-label="' + m[2] + '" onclick="AV.tv(\'' + m[0] + '\', \'' + m[2] + '\')"' + (tvBusy ? ' disabled' : '') + '>' + icon(m[1]) + '</button>').join('') +
        '<button class="flat" aria-label="Volume up" onclick="AV.tv(\'volume_up\', \'Volume up\')"' + (tvBusy ? ' disabled' : '') + '>' + icon('vol') + '</button></div></div>' +
      later('Smart Switch', 'a-sky', 'remote', '<div class="hm-mode"><span>Quick toggle</span>' + AV.toggleHtml(false, 'green', '', true) + '</div>') +
      later('Water Motor', 'a-slate', 'motor', '<div class="hm-mode"><span>Off / On</span><span class="hm-pw">' + icon('power') + icon('x', 'dim') + '</span></div>') +
      later('Washing Machine', 'a-navy', 'washer', '<div class="hm-grow"><svg class="hm-ring" viewBox="0 0 40 40"><circle cx="20" cy="20" r="15"/><path d="M20 5a15 15 0 0 1 14.3 10.4"/></svg><b class="hm-muted">Idle</b></div>');
  };
  /* ---------- presence automation card ---------- */
  AV.pres = () => (L.body && L.body.presence) || null;
  AV.presCfg = async patch => {
    try{ const r = await api('/presence/config', { method:'POST', body:patch }); if(L.body) L.body.presence = r.presence; AV.paint(); }
    catch(e){ A.toast(errMsg(e)); }
  };
  AV.presSnooze = async m => {
    try{ const r = await api('/presence/snooze', { method:'POST', body:{ minutes:m } }); if(L.body) L.body.presence = r.presence; AV.paint(); A.toast(m ? 'Paused for ' + (m >= 60 ? (m / 60) + ' h' : m + ' min') : 'Resumed'); }
    catch(e){ A.toast(errMsg(e)); }
  };
  AV.presMin = d => { const p = AV.pres(); if(p) AV.presCfg({ empty_min: Math.max(3, Math.min(180, p.empty_min + d)) }); };
  AV.presHtml = () => {
    const p = AV.pres();
    if(!p) return '<div class="hm-card hm-pres"><div class="hm-th"><span>Auto-off when the room is empty</span></div><div class="hm-note">Not available on this server yet.</div></div>';
    const mins = s => s >= 3600 ? Math.round(s / 360) / 10 + ' h' : Math.max(1, Math.round(s / 60)) + ' min';
    let line = p.state === 'unknown' ? 'Waiting for the room sensors…' : p.state === 'present' ? 'Someone is in the room' : 'Room empty for ' + mins(p.since_s);
    if(p.enabled && p.snooze_s > 0) line += ' · paused for ' + mins(p.snooze_s);
    else if(p.enabled && p.would_act_in_s != null) line += ' · switching off in ' + mins(Math.max(60, p.would_act_in_s));
    const last = p.events && p.events.length ? p.events[p.events.length - 1] : null;
    return '<div class="hm-card hm-pres"><div class="hm-th"><span>Auto-off when the room is empty</span>' +
      AV.toggleHtml(p.enabled, 'green', 'AV.presCfg({enabled:' + (!p.enabled) + '})', false) + '</div>' +
      '<div class="hm-psub">' + E(line) + '</div>' +
      '<div class="hm-prow2"><span>Switch off after</span><div class="hm-step"><button aria-label="Fewer minutes" onclick="AV.presMin(-5)">' + icon('minus') + '</button><b>' + p.empty_min + ' min</b><button aria-label="More minutes" onclick="AV.presMin(5)">' + icon('plus') + '</button></div></div>' +
      '<div class="hm-prow2"><span>Also the fan</span>' + AV.toggleHtml(p.fan, 'green', 'AV.presCfg({fan:' + (!p.fan) + '})', false) + '</div>' +
      '<div class="hm-prow2"><span>Switch them back on when I return</span>' + AV.toggleHtml(p.restore, 'green', 'AV.presCfg({restore:' + (!p.restore) + '})', false) + '</div>' +
      '<div class="hm-snz"><button onclick="AV.presSnooze(30)">Pause 30 min</button><button onclick="AV.presSnooze(120)">2 h</button><button onclick="AV.presSnooze(480)">8 h</button>' +
        (p.snooze_s > 0 ? '<button onclick="AV.presSnooze(0)">Resume</button>' : '') + '</div>' +
      (last ? '<div class="hm-foot">' + E(A.ago(last.at * 1000)) + ': ' + E(last.text) + '</div>' : '') +
      '<div class="hm-foot">Only acts when the radar and motion sensor both see nobody and the box is online. Plug and TV are never touched.</div></div>';
  };

  AV.irHtml = () => {
    const b = (L.body && L.body.avbox) || {}, names = b.ir_buttons || [];
    return (names.length ? '<div class="hm-ir">' + names.map(n =>
      '<button onclick="AV.ir(\'send\', ' + E(JSON.stringify(n)) + ')"' + (AV.busy ? ' disabled' : '') + '>' + E(n) + '</button>').join('') + '</div>'
      : '<div class="hm-card hm-empty">No remote buttons learned yet.</div>') +
      (b.last_ir ? '<div class="hm-foot">Last: ' + E(b.last_ir.op) + ' "' + E(b.last_ir.name) + '" — ' + E(b.last_ir.msg) + '</div>' : '');
  };

  AV.paint = () => {
    if(!$('hmRoot')) return;
    const b = (L.body && L.body.avbox) || {}, link = L.body ? L.body.link : null;
    const pills = $('hmPills');
    if(pills) pills.innerHTML = link === false ? '<span class="hm-pill bad">server cannot reach the box</span>' :
      (b.online === true ? '<span class="hm-pill ok">Box online</span>' : b.online === false ? '<span class="hm-pill bad">Box offline</span>' : '<span class="hm-pill">Box status unknown</span>') +
      (b.seen_s != null ? '<span class="hm-pill amber">updated ' + Math.round(b.seen_s) + ' s ago</span>' : '');
    const set = (id, html) => { const el = $(id); if(el) el.innerHTML = html; };
    set('hmEnv', AV.envHtml());
    const dragging = document.activeElement && document.activeElement.type === 'range';   // never yank a slider mid-drag
    set('hmFan', AV.fanHtml());
    if(!dragging){ set('hmCeil1', AV.ceilHtml('ceiling1', 'Ceiling Light 1', 'sun')); set('hmCeil2', AV.ceilHtml('ceiling2', 'Ceiling Light 2', 'lamp')); }
    set('hmRow3', AV.smallHtml('bulb', 'Bulb Light', 'bulb', 'amber') + AV.smallHtml('tube', 'Tube Light', 'tube', 'white') + AV.smallHtml('general', 'General Switch', 'power', 'green'));
    if(!dragging) set('hmPres', AV.presHtml());
    set('hmApps', AV.appsHtml());
    if(!AV.busy) set('hmIr', AV.irHtml());
    const h = L.body && L.body.home, st = $('hmHomeSt');
    if(st) st.textContent = !h || !h.state ? 'Reading your devices…' : (h.state.lights && !h.state.lights.ok ? 'Lights: ' + (h.state.lights.err || 'unreachable') + '. ' : '') +
      'Devices read ' + (h.age_s == null ? '' : Math.round(h.age_s) + ' s ago');
  };
  AV.refresh = async force => { try{ await api('/home/refresh', { method:'POST', body:{ force: !!force } }); }catch(e){ if(force) A.toast(errMsg(e)); } };

  AV.ir = async (op, name) => {
    if(AV.busy) return;
    if(op === 'learn'){
      const f = $('avLearn'); name = (f ? f.value : '').trim().toLowerCase();
      if(!name){ A.toast('Give the button a name first'); return; }
    }
    AV.busy = op;
    const msg = $('avIrMsg');
    if(msg) msg.textContent = op === 'learn' ? 'Point the remote at the box and press "' + name + '" once (25 s)…' : op === 'send' ? 'Sending "' + name + '"…' : 'Forgetting…';
    try{
      const r = await api('/avbox/ir', { method:'POST', body:{ op, name } });
      if(msg) msg.textContent = r.msg || (r.ok ? 'Done' : 'Failed');
      if(op === 'learn' && r.ok){ const f = $('avLearn'); if(f) f.value = ''; }
      A.toast(r.ok ? (op === 'send' ? 'Sent' : op === 'learn' ? 'Learned' : 'Forgotten') : 'Did not work');
    }catch(e){ if(msg) msg.textContent = errMsg(e); }
    finally{ AV.busy = null; AV.paint(); }
  };
  AV.forget = () => {
    const names = (L.body && L.body.avbox && L.body.avbox.ir_buttons) || [];
    if(!names.length){ A.toast('Nothing to forget'); return; }
    openSheet('<h3>Forget a button</h3><div class="card">' + names.map(n =>
      '<button class="m-item" onclick="closeSheet();AV.ir(\'forget\', ' + E(JSON.stringify(n)) + ')"><div class="grow"><b>' + E(n) + '</b></div></button>').join('') + '</div>' +
      '<div class="sheet-actions"><button class="btn btn-ghost" onclick="closeSheet()">Cancel</button></div>');
  };
  AV.show = async () => {
    const f = $('avOled'), text = f ? f.value.trim() : '';
    if(!text) return;
    try{ await api('/avbox/display', { method:'POST', body:{ text } }); if(f) f.value = ''; A.toast('On the box screen'); }
    catch(e){ A.toast(errMsg(e)); }
  };

  AV.render = el => {
    if(el.querySelector('#hmRoot')){ AV.paint(); AV.startPoll(); return; }   // keep sliders / typed text on background re-renders
    if(!configured()){ el.innerHTML = A.head('Bedroom') + '<div class="m-note">Connect Almanac to your Layla server first (tap the sync dot at the top).</div>'; return; }
    el.innerHTML = '<div class="hm-root" id="hmRoot">' +
      '<div class="hm-top"><button class="hm-back" aria-label="Back" onclick="ALM.back()">' + icon('back') + '</button>' +
        '<div class="hm-title"><h2>Bedroom &amp; Appliances</h2><div class="hm-pills" id="hmPills"></div></div>' +
        '<button class="hm-avatar" aria-label="Refresh devices" onclick="AV.refresh(true)">' + icon('refresh') + '</button></div>' +
      '<div class="hm-sec">Environment &amp; System</div><div class="hm-env" id="hmEnv"></div>' +
      '<div class="hm-sec">Bedroom Switch Board</div>' +
      '<div class="hm-board"><div class="hm-card hm-fan" id="hmFan"></div><div class="hm-card hm-ceil" id="hmCeil1"></div><div class="hm-card hm-ceil" id="hmCeil2"></div></div>' +
      '<div class="hm-row3" id="hmRow3"></div>' +
      '<div class="hm-foot" id="hmHomeSt"></div>' +
      '<div class="hm-sec">Automation</div><div id="hmPres"></div>' +
      '<div class="hm-sec">Appliances &amp; Utilities</div><div class="hm-apps" id="hmApps"></div>' +
      '<div class="hm-sec hm-sec2"><span>Remote Buttons</span><button onclick="AV.forget()">Forget</button></div><div id="hmIr"></div><div id="avIrMsg" class="hm-foot"></div>' +
      '<div class="hm-card hm-form"><label for="avLearn">Teach a new button</label><input id="avLearn" maxlength="40" placeholder="e.g. tv power, ac on">' +
        '<button onclick="AV.ir(\'learn\')">Learn from the remote</button></div>' +
      '<div class="hm-card hm-form row"><input id="avOled" maxlength="40" placeholder="Short message for the box screen"><button onclick="AV.show()">Show</button></div>' +
      '</div>';
    AV.paint();
    AV.startPoll();
    AV.refresh(true);
    if(RT() && !RT().ws && !RT().dead) RT().connect();
    if(!(RT() && RT().send({ t:'body.get' }))) L.pull();
  };
  AV.startPoll = () => {
    if(AV.poll) return;
    AV.poll = setInterval(() => { if(!modOpen('avbox')){ clearInterval(AV.poll); AV.poll = null; return; } if(!document.hidden) AV.refresh(false); }, 20000);
  };

  A.reg({ id:'avbox', title:'Bedroom', icon:'sensor', desc:'AV box, lights & appliances', group:'layla', render: AV.render,
    badge: () => { const s = L.body && L.body.avbox && L.body.avbox.sensors, t = s && s.room_temperature;
      return t && t.v != null ? t.v.toFixed(1) + '°C' + (s.room_humidity && s.room_humidity.v != null ? ' · ' + Math.round(s.room_humidity.v) + '%' : '') : ''; },
    chip: () => { const s = L.body && L.body.avbox && L.body.avbox.sensors, t = s && s.room_temperature;
      return t && t.v != null ? { k:'Room', v: t.v.toFixed(1) + '°C' } : null; } });

  /* ======================================================= PHONE & WHATSAPP (native, Android app only) =======================================================
     Layla's two on-phone agents live inside this app now. This screen shows what the phone has granted, lets the owner fix
     each missing item with one tap, and is the app-side kill switch for WhatsApp auto-replies (same switch as Telegram /wa). */
  const PH = root.PH = { st:null, wa:null, waErr:'', busy:false, timer:null };
  const nat = () => { try{ const c = root.Capacitor; return (c && c.isNativePlatform && c.isNativePlatform()) ? c.registerPlugin('LaylaNative') : null; }catch(e){ return null; } };
  const dot = ok => '<i class="ph-dot ' + (ok ? 'ok' : 'bad') + '"></i>';

  PH.refresh = async () => {
    const n = nat(); if(!n) return;
    try{ PH.st = await n.status(); }catch(e){ PH.st = null; }
    if(PH.st && PH.st.wa && PH.st.wa.serverConfigured){
      try{ PH.wa = await n.waStatus(); PH.waErr = ''; }catch(e){ PH.wa = null; PH.waErr = errMsg(e); }
    }
    if(modOpen('phone')) PH.paint();
  };
  PH.go = async (fn, okMsg) => {
    const n = nat(); if(!n || PH.busy) return;
    PH.busy = true;
    try{ await fn(n); if(okMsg) A.toast(okMsg); }catch(e){ A.toast(errMsg(e)); }
    PH.busy = false; setTimeout(PH.refresh, 600);
  };
  PH.perms = () => PH.go(n => n.askPermissions());
  PH.open = t => PH.go(n => n.openSettings({ target:t }));
  PH.start = () => PH.go(n => n.startPhone(), 'Phone agent started');
  PH.power = on => PH.go(n => n.waPower({ on }), on ? 'WhatsApp auto-reply is ON' : 'WhatsApp auto-reply is OFF');
  PH.askOn = () => A.ask('Turn WhatsApp auto-reply on?', 'Layla will reply on your behalf, as your assistant, to people who are NOT saved in your contacts. Saved contacts are never answered. You can switch it off here or with /wa off in Telegram at any time.', 'Turn on', () => PH.power(true));

  PH.row = (ok, label, detail, btn, js) => '<div class="ph-row">' + dot(ok) + '<div class="grow"><b>' + E(label) + '</b><small>' + E(detail) + '</small></div>' +
    (!ok && btn ? '<button class="ph-btn" onclick="' + js + '">' + E(btn) + '</button>' : '') + '</div>';

  PH.paint = () => {
    const el = $('phBody'); if(!el) return;
    const st = PH.st, w = PH.wa;
    if(!st){ el.innerHTML = '<div class="ph-note">Reading the phone…</div>'; return; }
    const ph = st.phone, wl = st.wa;
    const on = !!(w && w.enabled);
    const rec = (w && w.recent || []).slice(0, 5).map(r => '<div class="ph-rec"><b>' + E(r.title) + '</b><span class="' + (r.status === 'sent' ? 'g' : r.status === 'failed' ? 'r' : '') + '">' + E(r.status) + '</span>' +
      '<p>' + E(r.text) + '</p><small>' + E(A.ago(r.ts * 1000)) + '</small></div>').join('');
    el.innerHTML =
      '<div class="ph-sec">WhatsApp auto-reply</div><div class="ph-card">' +
        '<div class="ph-head"><div class="grow"><b>' + (!w ? 'Status unknown' : on ? 'Replying to strangers' : 'Off') + '</b><small>' +
          (w ? (on ? 'Answers people not saved in your contacts, as your assistant. Saved contacts never get an automatic reply.' : 'Nothing is sent automatically while this is off.') : (PH.waErr || (wl.serverConfigured ? 'Could not reach the server' : 'This build has no WhatsApp server settings'))) + '</small></div>' +
          (w ? '<button class="hm-tg green' + (on ? ' on' : '') + '" role="switch" aria-checked="' + on + '" onclick="' + (on ? 'PH.power(false)' : 'PH.askOn()') + '"><i></i></button>' : '') + '</div>' +
        (w ? '<div class="ph-meta">' + w.sent_24h + ' sent in the last 24 h · WhatsApp and WhatsApp Business · spam and links are ignored · max 3 replies per stranger per hour</div>' : '') +
        PH.row(wl.listener, 'Reading WhatsApp notifications', wl.listener ? 'On' : 'Off: replies cannot be sent. Find "Layla WhatsApp replies" and turn it on.', 'Open Notification access', "PH.open('notification')") +
        (rec ? '<div class="ph-sub">Latest replies</div>' + rec : '') +
      '</div>' +
      '<div class="ph-sec">Phone agent</div><div class="ph-card">' +
        PH.row(ph.permissionsMissing === 0, 'Calls, SMS and contacts', ph.permissionsMissing === 0 ? 'Granted' : ph.permissionsMissing + ' permission(s) still needed', 'Grant', 'PH.perms()') +
        PH.row(ph.accessibility, 'App control (tapping, typing)', ph.accessibility ? 'On' : 'Off: find "Layla app control". If it is greyed out: App info → ⋮ → Allow restricted settings.', 'Open Accessibility', "PH.open('accessibility')") +
        PH.row(ph.notificationReader, 'Reading your notifications', ph.notificationReader ? 'On' : 'Off: Layla cannot tell you who messaged you', 'Open Notification access', "PH.open('notification')") +
        PH.row(ph.batteryUnrestricted, 'Battery: run without restrictions', ph.batteryUnrestricted ? 'Exempt' : 'Restricted: the phone may close the connection in the background', 'Allow', "PH.open('battery')") +
        PH.row(ph.overlay, 'Approval popup over other apps', ph.overlay ? 'Allowed' : 'Not allowed: approvals still arrive as a notification', 'Allow', "PH.open('overlay')") +
        '<div class="ph-head" style="margin-top:6px"><div class="grow"><b>Agent connection</b><small>Always asks you before placing a call or sending an SMS or WhatsApp message.</small></div><button class="ph-btn" onclick="PH.start()">Start / restart</button></div>' +
      '</div>' +
      '<div class="ph-note">On Vivo/Funtouch phones also set: Battery → Background power consumption → Layla → Allow, and Autostart → on. Lock this app in Recents so clearing apps does not close it. If you still have the old "Layla Phone Agent" or "Layla WhatsApp" apps installed, uninstall them so nothing answers twice.</div>';
  };

  PH.render = el => {
    if(el.querySelector('#phBody')){ PH.paint(); PH.refresh(); return; }
    if(!nat()){
      el.innerHTML = A.head('Phone & WhatsApp') + '<div class="ph-note">The phone and WhatsApp agents run inside the Almanac Android app. Open this screen there.</div>';
      return;
    }
    el.innerHTML = '<div class="ph-root" id="phRoot">' + A.head('Phone & WhatsApp', { sub:'Layla\'s agents on this phone' }) + '<div id="phBody"></div></div>';
    PH.paint(); PH.refresh();
    clearInterval(PH.timer);
    PH.timer = setInterval(() => { if(!modOpen('phone')){ clearInterval(PH.timer); return; } if(!document.hidden) PH.refresh(); }, 15000);
  };
  document.addEventListener('visibilitychange', () => { if(!document.hidden && modOpen('phone')) PH.refresh(); });   // back from a Settings page

  A.reg({ id:'phone', title:'Phone & WhatsApp', icon:'phone', desc:'Phone agent and auto-reply', group:'layla', render: PH.render,
    badge: () => PH.wa ? (PH.wa.enabled ? 'Auto-reply ON' : 'Auto-reply off') : '' });

  A.on('boot', () => { if(configured() && !A.isMember()) setTimeout(L.pull, 1500); });
})(typeof window !== 'undefined' ? window : globalThis);
