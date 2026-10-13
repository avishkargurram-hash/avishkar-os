/* Almanac modules: core registry, shared helpers, More hub and the hooks index.html calls into.
   Every module registers itself with ALM.reg({id,title,icon,desc,group,render(el,sub),chip()}). */
(function(root){
  'use strict';
  const A = root.ALM = { mods:{}, order:[], cur:null, sub:null, hooks:{} };
  const $ = id => document.getElementById(id);
  A.$ = $;

  /* Escapes quotes too, so values are safe inside both text and attribute contexts. */
  const E = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  A.E = E;
  /* For values placed inside onclick="fn('...')": ids are [A-Za-z0-9_-] already, this guards anything else. */
  A.J = s => String(s == null ? '' : s).replace(/[^A-Za-z0-9_-]/g, '');

  const IC = {
    folder:'<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    list:'<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2"/>',
    cart:'<circle cx="9" cy="20" r="1.4"/><circle cx="18" cy="20" r="1.4"/><path d="M3 4h2.5l2.2 11h10.6l2-8H6.5"/>',
    wallet:'<path d="M4 7a2 2 0 0 1 2-2h11v4"/><path d="M4 7v10a2 2 0 0 0 2 2h13a1 1 0 0 0 1-1V10a1 1 0 0 0-1-1H6a2 2 0 0 1-2-2z"/><circle cx="16.5" cy="14" r="1.2"/>',
    heart:'<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.4A4 4 0 0 1 19 10c0 5.600-7 10-7 10z"/><path d="M8 12h2l1.500-2.500 2 4L15 12h1"/>',
    file:'<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    key:'<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M16 7l3 3M14 9l2 2"/>',
    alarm:'<circle cx="12" cy="13" r="7.500"/><path d="M12 9v4l2.500 1.500M4 5l3-2M20 5l-3-2"/>',
    clip:'<rect x="6" y="4" width="12" height="17" rx="2"/><path d="M9 4V3h6v1M9.500 10h5M9.500 14h5"/>',
    family:'<circle cx="9" cy="8" r="3"/><circle cx="17" cy="9.500" r="2.300"/><path d="M3 20c0-3.500 2.700-6 6-6s6 2.500 6 6M15.500 14.500c2.800 0 5 2 5 5"/>',
    lock:'<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    plus:'<path d="M12 5v14M5 12h14"/>',
    trash:'<path d="M4 7h16M10 7V4h4v3M6 7l1 13h10l1-13"/>',
    search:'<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.500-4.500"/>',
    copy:'<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
    eye:'<path d="M2 12s3.500-6.500 10-6.500S22 12 22 12s-3.500 6.500-10 6.500S2 12 2 12z"/><circle cx="12" cy="12" r="2.500"/>',
    eyeoff:'<path d="M3 3l18 18M10.500 6c.5-.1 1-.1 1.500-.1 6.500 0 10 6.100 10 6.100a17 17 0 0 1-3.300 4M6.500 7.500A17 17 0 0 0 2 12s3.500 6.500 10 6.500c1.500 0 2.800-.3 4-.9"/>',
    back:'<path d="M15 5l-7 7 7 7"/>',
    more:'<circle cx="5" cy="12" r="1.500"/><circle cx="12" cy="12" r="1.500"/><circle cx="19" cy="12" r="1.500"/>',
    grid:'<rect x="4" y="4" width="7" height="7" rx="1.500"/><rect x="13" y="4" width="7" height="7" rx="1.500"/><rect x="4" y="13" width="7" height="7" rx="1.500"/><rect x="13" y="13" width="7" height="7" rx="1.500"/>',
    send:'<path d="M21 3L3 10.500l7 3 3 7z"/><path d="M10 13.500L21 3"/>',
    dice:'<rect x="4" y="4" width="16" height="16" rx="3"/><circle cx="9" cy="9" r="1"/><circle cx="15" cy="15" r="1"/><circle cx="15" cy="9" r="1"/><circle cx="9" cy="15" r="1"/>',
    paperclip:'<path d="M20 11l-8.500 8.500a5 5 0 0 1-7-7L13 4a3.500 3.500 0 0 1 5 5l-8.500 8.500a2 2 0 0 1-3-3L14 7"/>',
    bell:'<path d="M6 17V11a6 6 0 0 1 12 0v6l1.500 2h-15z"/><path d="M10 21h4"/>',
    edit:'<path d="M4 20h4L19 9l-4-4L4 16z"/>'
  };
  A.icon = (n, big) => '<svg class="' + (big ? 'icon-lg' : 'icon') + '" viewBox="0 0 24 24">' + (IC[n] || IC.folder) + '</svg>';

  /* ---------- hooks ---------- */
  A.on = (name, fn) => { (A.hooks[name] = A.hooks[name] || []).push(fn); };
  A.fire = (name, a, b) => { (A.hooks[name] || []).forEach(fn => { try{ fn(a, b); }catch(e){ console.error('ALM hook ' + name, e); } }); };

  /* ---------- registry ---------- */
  A.reg = m => { A.mods[m.id] = m; if(A.order.indexOf(m.id) < 0) A.order.push(m.id); };
  A.GROUPS = [['app','Everyday'], ['plan','Planning'], ['vault','Private vaults (encrypted on this device)'], ['live','Live & family']];

  /* ---------- record store (DB.mod / DB.vault / DB.fam) ---------- */
  const KS = { prj:'mod', chk:'mod', shop:'mod', exp:'mod', alm:'mod', vh:'vault', vd:'vault', vp:'vault', fshop:'fam', fev:'fam' };
  A.KS = KS;
  A.store = k => { const r = DB[KS[k]] || (DB[KS[k]] = {}); return r[k] || (r[k] = {}); };
  A.get = (k, id) => A.store(k)[id] || null;
  A.list = k => Object.entries(A.store(k)).map(([id, r]) => Object.assign({ id }, r));
  A.put = (k, id, rec) => { const v = Object.assign({}, rec); delete v.id; A.store(k)[id] = v; save(); return id; };
  A.del = (k, id) => { delete A.store(k)[id]; save(); };
  A.uid = () => uid();

  /* ---------- formatting ---------- */
  A.money = (n, sign) => {
    n = Number(n) || 0;
    const s = Math.abs(n).toLocaleString('en-IN', { maximumFractionDigits: 2, minimumFractionDigits: (Math.abs(n) % 1 ? 2 : 0) });
    return (n < 0 ? '-' : (sign && n > 0 ? '+' : '')) + '₹' + s;
  };
  const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  A.MON = MON;
  A.fdate = ds => { const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(ds || ''); return m ? (+m[3]) + ' ' + MON[+m[2] - 1] + (m[1] !== todayStr().slice(0, 4) ? ' ' + m[1] : '') : ''; };
  A.ftime = t => { const m = /^(\d{1,2}):(\d{2})$/.exec(t || ''); if(!m) return ''; const h = +m[1]; return ((h % 12) || 12) + ':' + m[2] + ' ' + (h < 12 ? 'AM' : 'PM'); };
  A.ago = ms => {
    const s = Math.max(0, Math.round((Date.now() - ms) / 1000));
    if(s < 45) return 'just now'; if(s < 3600) return Math.round(s / 60) + ' min ago';
    if(s < 86400) return Math.round(s / 3600) + ' h ago'; return Math.round(s / 86400) + ' d ago';
  };

  /* ISO week key; must equal Python's f"{y}-W{w:02d}" from date.isocalendar() for the same UTC date. */
  A.isoWeek = ds => {
    const d = new Date(ds + 'T00:00:00Z');
    d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7) + 3);
    const y = d.getUTCFullYear(), j = new Date(Date.UTC(y, 0, 4));
    const w = 1 + Math.round(((d - j) / 864e5 - 3 + ((j.getUTCDay() + 6) % 7)) / 7);
    return y + '-W' + String(w).padStart(2, '0');
  };
  A.periodKey = (tier, ds) => { ds = ds || todayStr(); return tier === 'weekly' ? A.isoWeek(ds) : tier === 'monthly' ? ds.slice(0, 7) : ds; };

  /* ---------- toast / confirm ---------- */
  let toastT = null;
  A.toast = (msg, label, fn) => {
    let t = $('mToast');
    if(!t){ t = document.createElement('div'); t.id = 'mToast'; t.className = 'm-toast'; t.setAttribute('role', 'status'); document.body.appendChild(t); }
    t.innerHTML = E(msg) + (label ? '<button type="button" id="mToastBtn">' + E(label) + '</button>' : '');
    t.classList.add('show');
    if(label){ const b = $('mToastBtn'); b.onclick = () => { t.classList.remove('show'); try{ fn && fn(); }catch(e){} }; }
    clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('show'), label ? 7000 : 2600);
  };
  let askFn = null;
  A.ask = (title, msg, okLabel, fn, danger) => {
    askFn = fn;
    openSheet('<h3>' + E(title) + '</h3><p class="muted" style="font-size:14px;line-height:1.5">' + E(msg) + '</p>' +
      '<div class="sheet-actions"><button class="btn btn-ghost" onclick="closeSheet()">Cancel</button>' +
      '<button class="btn btn-primary' + (danger ? ' btn-danger' : '') + '" onclick="ALM._askOk()">' + E(okLabel || 'OK') + '</button></div>');
  };
  A._askOk = () => { const f = askFn; askFn = null; closeSheet(); try{ f && f(); }catch(e){ console.error(e); } };

  A.head = (title, opts) => {
    opts = opts || {};
    return '<div class="m-head"><button class="m-back" aria-label="Back" onclick="ALM.back()">' + A.icon('back') + '</button><h2>' + E(title) + '</h2>' +
      (opts.add ? '<button class="m-add" aria-label="' + E(opts.addLabel || 'Add') + '" onclick="' + opts.add + '">' + A.icon('plus') + '</button>' : '') + '</div>' +
      (opts.sub ? '<div class="m-sub">' + opts.sub + '</div>' : '');
  };

  /* ---------- navigation ---------- */
  A.open = (id, sub) => {
    if(!A.mods[id] || !A.visible(A.mods[id])) return;
    A.cur = id; A.sub = sub || null;
    if(currentView === 'mod') A.renderMod(); else go('mod');
  };
  A.back = () => { if(A.sub){ A.sub = null; A.renderMod(); window.scrollTo(0, 0); } else go('more'); };
  A.sub_ = s => { A.sub = s || null; A.renderMod(); window.scrollTo(0, 0); };
  A.renderMod = () => {
    const el = $('modBody'), m = A.mods[A.cur];
    if(!el) return;
    if(!m){ el.innerHTML = ''; return; }
    try{ m.render(el, A.sub); }
    catch(e){ console.error(e); el.innerHTML = A.head(m.title) + '<div class="m-err">Something went wrong showing this section.</div>'; }
  };
  A.renderMore = () => {
    const el = $('moreBody'); if(!el) return;
    let h = '<div class="m-head"><h2 style="margin-left:2px">More</h2></div>';
    for(const [g, label] of A.GROUPS){
      const ms = A.order.map(i => A.mods[i]).filter(m => m.group === g && A.visible(m));
      if(!ms.length) continue;
      h += '<div class="m-group">' + E(label) + '</div><div class="m-grid">';
      for(const m of ms){
        let s = m.desc || '';
        try{ if(m.badge) s = m.badge() || s; }catch(e){}
        h += '<button class="m-tile ' + (g === 'vault' ? 'vault' : g === 'live' ? 'live' : '') + '" onclick="' + (m.go ? 'go(\'' + m.go + '\')' : 'ALM.open(\'' + m.id + '\')') + '">' +
          '<span class="m-ic">' + A.icon(m.icon) + '</span><span><b>' + E(m.title) + '</b><span class="s">' + E(s) + '</span></span>' +
          (g === 'vault' ? '<span class="m-tlock">' + A.icon('lock') + '</span>' : '') + '</button>';
      }
      h += '</div>';
    }
    el.innerHTML = h;
  };

  /* Home widget: one short chip per module that has something to say. */
  A.afterHome = () => {
    const el = $('homeMods'); if(!el) return;
    const chips = [];
    for(const id of A.order){
      const m = A.mods[id]; if(!m.chip || !A.visible(m)) continue;
      try{ const c = m.chip(); if(c) chips.push('<button class="m-chip" onclick="ALM.open(\'' + id + '\')"><small>' + E(c.k) + '</small><b>' + E(c.v) + '</b></button>'); }catch(e){}
    }
    el.innerHTML = chips.length ? '<div class="section-title">Your modules <span class="link" onclick="go(\'more\')">All</span></div><div class="m-chips">' + chips.join('') + '</div>' : '';
  };

  /* Called by index.html whenever local data changes / sync applies remote changes / a state pull lands. */
  A.saved = () => A.fire('saved');
  A.afterSync = kinds => { A.fire('afterSync', kinds); };
  A.onState = (sp, resp) => A.fire('state', sp, resp);
  A.refresh = () => {
    if(currentView === 'more') A.renderMore();
    else if(currentView === 'mod') A.renderMod();
    A.fire('refresh');
  };
  A.boot = () => A.fire('boot');
  A.isMember = () => root.SYNC_MODE === 'member';
  A.visible = m => !(A.isMember() && !m.member);

  /* Secret text that lives on the clipboard for a short while only. */
  A.copyText = async (text, clearAfterMs) => {
    try{ await navigator.clipboard.writeText(text); }
    catch(e){
      const t = document.createElement('textarea'); t.value = text; t.style.position = 'fixed'; t.style.opacity = '0';
      document.body.appendChild(t); t.select(); try{ document.execCommand('copy'); }catch(_){} t.remove();
    }
    if(clearAfterMs){ setTimeout(() => { try{ navigator.clipboard.writeText(' '); }catch(e){} }, clearAfterMs); }
  };
})(typeof window !== 'undefined' ? window : globalThis);
