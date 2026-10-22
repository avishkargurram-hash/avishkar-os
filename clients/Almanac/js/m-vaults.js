/* Almanac zero-knowledge vaults: Health & Medical, Documents & Certificates, Passwords & Secrets.
   Everything is sealed on this device (AES-GCM, key from PBKDF2 of the master password) before it is stored or synced.
   The server and the sync log only ever see ciphertext; plaintext lives in memory (V.data) while the vault is unlocked. */
(function(root){
  'use strict';
  const A = root.ALM, E = A.E, J = A.J, $ = A.$, VC = root.VaultCrypto;
  const PLAIN_MAX = 300000, FILE_BUDGET = 280000, PDF_MAX_RAW = 200000;
  const IMG_STEPS = [[1600, .72], [1280, .65], [1024, .6], [800, .55], [640, .5]];
  const KIND_IDS = ['vh', 'vd', 'vp'];

  const KINDS = {
    vh: { title:'Health & Medical', icon:'heart', desc:'Prescriptions, reports, scans', files:true, noun:'record',
      cats:[['prescription','Prescription'], ['report','Report / scan'], ['lab','Lab result'], ['visit','Visit notes'], ['other','Other']],
      fields:[['doctor','Doctor / clinic','text'], ['date','Date','date']] },
    vd: { title:'Documents', icon:'file', desc:'Legal, contracts, credentials', files:true, noun:'document',
      cats:[['legal','Legal'], ['contract','Contract'], ['certificate','Certificate'], ['id','ID / licence'], ['other','Other']],
      fields:[['issuer','Issued by','text'], ['number','Number / reference','text'], ['date','Issued','date'], ['expires','Expires','date']] },
    vp: { title:'Passwords', icon:'key', desc:'Logins and secrets', files:false, noun:'secret',
      cats:[['login','Login'], ['card','Card'], ['wifi','Wi-Fi'], ['note','Secret note'], ['other','Other']],
      fields:[['user','Username / email','text'], ['pass','Password / secret','secret'], ['url','Website','text']] }
  };
  const catLabel = (K, c) => { const f = K.cats.find(x => x[0] === c); return f ? f[1] : 'Other'; };

  const V = root.V = { key:null, data:{ vh:{}, vd:{}, vp:{} }, refs:{ vh:{}, vd:{}, vp:{} }, bad:new Set(), metaSig:null,
    q:{}, shown:{}, fails:0, until:0, busy:false, hiddenAt:0, lastAct:Date.now(), draft:null, _q:Promise.resolve() };

  const meta = () => { const m = DB.vault && DB.vault.vmeta; return (m && typeof m.salt === 'string' && typeof m.ver === 'string' && Number.isInteger(m.iter)) ? m : null; };
  const metaSig = m => m ? m.salt + '|' + m.ver + '|' + m.iter : '';
  const secure = () => !!(root.crypto && root.crypto.subtle);
  const val = id => { const e = $(id); return e ? e.value.trim() : ''; };
  const inVault = () => (currentView === 'mod' && KINDS[A.cur]);
  const err = m => { const e = $('vErr'); if(e) e.textContent = m || ''; };

  /* ---------- key lifecycle ---------- */
  V.lock = function(){
    const had = !!V.key;
    V.key = null; V.data = { vh:{}, vd:{}, vp:{} }; V.refs = { vh:{}, vd:{}, vp:{} }; V.bad = new Set(); V.shown = {}; V.metaSig = null;
    if(V.draft){ V.draft = null; try{ closeSheet(); }catch(e){} }
    V.wipeTmp();
    if(had){ if(inVault()) A.renderMod(); else if(currentView === 'more') A.renderMore(); }
  };
  V.touch = () => { V.lastAct = Date.now(); };

  V.reload = () => (V._q = V._q.then(async () => {
    if(!V.key) return;
    const key = V.key;
    for(const k of KIND_IDS){
      const st = A.store(k), d = V.data[k], r = V.refs[k];
      for(const id of Object.keys(d)) if(!st[id]){ delete d[id]; delete r[id]; V.bad.delete(k + ':' + id); }
      for(const [id, rec] of Object.entries(st)){
        if(r[id] === rec) continue;
        try{ d[id] = await VC.open(key, rec, k + ':' + id); V.bad.delete(k + ':' + id); }
        catch(e){ delete d[id]; V.bad.add(k + ':' + id); }
        if(V.key !== key) return;
        r[id] = rec;
      }
    }
  }).catch(e => console.error('vault reload', e)));

  async function saveRec(k, id, obj){
    if(V.busy) throw new Error('busy');
    const sealed = await VC.seal(V.key, obj, k + ':' + id);
    A.put(k, id, sealed);
    V.data[k][id] = obj; V.refs[k][id] = A.get(k, id); V.bad.delete(k + ':' + id);
  }
  V.saveRec = saveRec;

  /* ---------- setup / unlock ---------- */
  V.strength = pw => {
    let c = 0; if(/[a-z]/.test(pw)) c++; if(/[A-Z]/.test(pw)) c++; if(/\d/.test(pw)) c++; if(/[^A-Za-z0-9]/.test(pw)) c++;
    const words = pw.trim().split(/\s+/).length;
    return Math.min(1, Math.min(pw.length, 20) / 20 * 0.65 + c * 0.09 + (words >= 4 ? 0.2 : 0));
  };
  V.meter = pw => {
    const s = V.strength(pw), i = document.querySelector('.m-meter i'); if(!i) return;
    i.style.width = Math.round(s * 100) + '%'; i.style.background = s < .45 ? 'var(--bad)' : s < .7 ? 'var(--warn)' : 'var(--ok)';
  };
  V.toggleType = id => { const e = $(id); if(e) e.type = e.type === 'password' ? 'text' : 'password'; };

  function lockHead(kind, title, text, body){
    const K = KINDS[kind];
    return A.head(K.title) + '<div class="m-lock"><div class="m-seal">' + A.icon('lock', true) + '</div><h3>' + title + '</h3><p>' + text + '</p>' + body + '</div>';
  }
  function setupView(kind, el){
    el.innerHTML = lockHead(kind, 'Create your vault password',
      'One password protects Health, Documents and Passwords. It never leaves this device and is not stored anywhere. <b>There is no recovery</b> - if you forget it, the contents cannot be opened by anyone.',
      '<form autocomplete="off" onsubmit="V.setup(event);return false"><div class="field"><label for="vPw1">Master password</label><div class="m-pw"><input id="vPw1" type="password" autocomplete="new-password" oninput="V.meter(this.value)"><button type="button" class="m-iconbtn" aria-label="Show password" onclick="V.toggleType(\'vPw1\')">' + A.icon('eye') + '</button></div></div>' +
      '<div class="m-meter"><i></i></div><div class="field"><label for="vPw2">Repeat it</label><input id="vPw2" type="password" autocomplete="new-password"></div>' +
      '<div class="m-err" id="vErr" role="alert"></div><button class="btn btn-primary btn-block" id="vGo" type="submit">Create vault</button>' +
      '<div class="m-note">Use at least 10 characters. A few random words works well. Other devices sync the encrypted data and ask for this same password.</div></form>');
  }
  function lockView(kind, el){
    el.innerHTML = lockHead(kind, 'Vault locked', 'Enter your master password to open Health, Documents and Passwords.',
      '<form autocomplete="off" onsubmit="V.unlock(event);return false"><div class="field"><label for="vPw">Master password</label><div class="m-pw"><input id="vPw" type="password" autocomplete="current-password"><button type="button" class="m-iconbtn" aria-label="Show password" onclick="V.toggleType(\'vPw\')">' + A.icon('eye') + '</button></div></div>' +
      '<div class="m-err" id="vErr" role="alert"></div><button class="btn btn-primary btn-block" id="vGo" type="submit">Unlock</button></form>');
    setTimeout(() => { const f = $('vPw'); if(f) f.focus(); }, 60);
  }

  V.setup = async ev => {
    if(ev) ev.preventDefault();
    const p1 = ($('vPw1') || {}).value || '', p2 = ($('vPw2') || {}).value || '';
    if(p1.length < 10){ err('Use at least 10 characters.'); return; }
    if(p1 !== p2){ err('The two passwords do not match.'); return; }
    const b = $('vGo'); if(b){ b.disabled = true; b.textContent = 'Creating...'; }
    try{
      if(typeof syncConfigured === 'function' && syncConfigured()){
        const ok = await syncPullState('main');
        if(!ok){ err('Cannot reach your Almanac server. Connect first so a second, conflicting vault is not created.'); return; }
        if(meta()){ A.toast('A vault already exists - enter its password.'); A.renderMod(); return; }
      }
      const r = await VC.createMeta(p1);
      DB.vault.vmeta = r.meta; V.key = r.key; V.metaSig = metaSig(r.meta);
      V.data = { vh:{}, vd:{}, vp:{} }; V.refs = { vh:{}, vd:{}, vp:{} };
      save(); V.touch(); A.toast('Vault created'); A.renderMod();
    }catch(e){ console.error(e); err('Could not create the vault: ' + (e && e.message || e)); }
    finally{ const b2 = $('vGo'); if(b2){ b2.disabled = false; b2.textContent = 'Create vault'; } }
  };

  V.unlock = async ev => {
    if(ev) ev.preventDefault();
    const m = meta(), pw = ($('vPw') || {}).value || '';
    if(!m || !pw) return;
    const wait = V.until - Date.now();
    if(wait > 0){ err('Too many attempts. Try again in ' + Math.ceil(wait / 1000) + 's.'); return; }
    const b = $('vGo'); if(b){ b.disabled = true; b.textContent = 'Unlocking...'; }
    let key = null;
    try{ key = await VC.unlock(pw, m); }catch(e){ err(String(e && e.message || e)); }
    if(!key){
      V.fails++; if(V.fails >= 3) V.until = Date.now() + Math.min(60000, 1000 * Math.pow(2, V.fails - 3));
      err('Wrong password.'); const b2 = $('vGo'); if(b2){ b2.disabled = false; b2.textContent = 'Unlock'; }
      const f = $('vPw'); if(f){ f.value = ''; f.focus(); }
      return;
    }
    V.fails = 0; V.until = 0; V.key = key; V.metaSig = metaSig(m);
    await V.reload(); V.touch();
    if(V.bad.size) A.toast(V.bad.size + ' item(s) could not be decrypted on this device.');
    A.renderMod();
  };

  /* ---------- list / detail ---------- */
  const cleanDays = ds => { const t = Date.parse(ds + 'T00:00:00'); return isNaN(t) ? null : Math.floor((t - Date.now()) / 864e5); };
  function expiryBadge(o){
    if(!o.expires) return '';
    const d = cleanDays(o.expires); if(d == null) return '';
    return d < 0 ? '<span class="m-badge bad">Expired</span>' : d <= 30 ? '<span class="m-badge gold">Expires in ' + d + 'd</span>' : '';
  }
  function sub(kind, o){
    const K = KINDS[kind], p = [catLabel(K, o.cat)];
    if(kind === 'vp' && o.user) p.push(o.user);
    if(kind === 'vh' && o.doctor) p.push(o.doctor);
    if(kind === 'vd' && o.issuer) p.push(o.issuer);
    if(kind !== 'vp' && o.date) p.push(A.fdate(o.date));
    return p.filter(Boolean).join(' · ');
  }
  function listHtml(kind){
    const q = (V.q[kind] || '').toLowerCase();
    const items = Object.entries(V.data[kind]).map(([id, o]) => Object.assign({ id }, o))
      .filter(o => !q || [o.title, o.notes, o.user, o.url, o.doctor, o.issuer, o.number, catLabel(KINDS[kind], o.cat)].join(' ').toLowerCase().includes(q))
      .sort((a, b) => String(a.title || '').localeCompare(String(b.title || '')));
    if(!items.length) return '<div class="card" style="margin-top:12px"><div class="empty">' + (q ? 'No matches.' : 'Nothing here yet. Tap + to add a ' + KINDS[kind].noun + '.') + '</div></div>';
    return '<div class="card" style="margin-top:12px">' + items.map(o =>
      '<button class="m-item" onclick="ALM.sub_(\'i:' + J(o.id) + '\')"><div class="grow"><b>' + E(o.title || 'Untitled') + '</b><div class="sub">' + E(sub(kind, o)) + '</div></div>' +
      expiryBadge(o) + (o.files && o.files.length ? '<span class="m-badge grey">' + o.files.length + ' file' + (o.files.length > 1 ? 's' : '') + '</span>' : '') + '</button>').join('') + '</div>';
  }
  function listView(kind, el){
    const K = KINDS[kind], n = Object.keys(V.data[kind]).length;
    el.innerHTML = A.head(K.title, { add:"V.edit('" + kind + "',null)", addLabel:'Add ' + K.noun, sub: n + ' item' + (n === 1 ? '' : 's') + ' &middot; encrypted on this device' }) +
      (V.bad.size ? '<div class="m-err">' + V.bad.size + ' item(s) could not be decrypted here (changed on another device?). Sync, then lock and unlock again.</div>' : '') +
      '<input class="m-search" id="vQ" type="search" placeholder="Search ' + E(K.title.toLowerCase()) + '" value="' + E(V.q[kind] || '') + '" oninput="V.find(\'' + kind + '\',this.value)" aria-label="Search">' +
      '<div id="vList">' + listHtml(kind) + '</div>' +
      '<div class="sheet-actions" style="margin-top:20px"><button class="btn btn-ghost" onclick="V.lock()">Lock now</button><button class="btn btn-ghost" onclick="V.settings()">Password &amp; reset</button></div>';
  }
  V.find = (kind, v) => { V.q[kind] = v; const l = $('vList'); if(l) l.innerHTML = listHtml(kind); V.touch(); };

  const kb = n => n < 1024 ? n + ' B' : Math.round(n / 1024) + ' KB';
  function detail(kind, el, id){
    const K = KINDS[kind], o = V.data[kind][id];
    if(!o){ A.sub = null; return listView(kind, el); }
    const jid = J(id);
    let rows = '<div class="m-kv"><small>Type</small><span>' + E(catLabel(K, o.cat)) + '</span></div>';
    for(const [f, label, type] of K.fields){
      if(!o[f]) continue;
      if(type === 'secret'){
        const vis = V.shown[id + ':' + f];
        rows += '<div class="m-kv"><small>' + E(label) + '</small><span class="m-secret">' + (vis ? E(o[f]) : '••••••••') + '</span>' +
          '<button class="m-iconbtn" aria-label="' + (vis ? 'Hide' : 'Show') + '" onclick="V.reveal(\'' + kind + '\',\'' + jid + '\',\'' + f + '\')">' + A.icon(vis ? 'eyeoff' : 'eye') + '</button>' +
          '<button class="m-iconbtn" aria-label="Copy" onclick="V.copy(\'' + kind + '\',\'' + jid + '\',\'' + f + '\')">' + A.icon('copy') + '</button></div>';
      }else{
        rows += '<div class="m-kv"><small>' + E(label) + '</small><span>' + (f === 'expires' ? E(A.fdate(o[f])) + ' ' + expiryBadge(o) : f === 'date' ? E(A.fdate(o[f])) : E(o[f])) + '</span>' +
          (f === 'user' || f === 'number' ? '<button class="m-iconbtn" aria-label="Copy" onclick="V.copy(\'' + kind + '\',\'' + jid + '\',\'' + f + '\')">' + A.icon('copy') + '</button>' : '') + '</div>';
      }
    }
    if(o.notes) rows += '<div class="m-kv"><small>Notes</small><span>' + E(o.notes) + '</span></div>';
    let files = '';
    if(o.files && o.files.length){
      files = '<div class="section-title">Attachments</div>' + o.files.map((f, i) =>
        (/^image\//.test(f.type) ? '<img class="m-thumb" alt="' + E(f.name) + '" src="' + E(f.data) + '" onclick="V.openFile(\'' + kind + '\',\'' + jid + '\',' + i + ')">' : '') +
        '<div class="m-file"><span class="grow">' + E(f.name) + ' &middot; ' + kb(Math.round(f.data.length * 0.75)) + '</span><button class="btn btn-ghost" style="padding:6px 12px;font-size:13px" onclick="V.openFile(\'' + kind + '\',\'' + jid + '\',' + i + ')">' + (/^image\//.test(f.type) ? 'Share' : 'Open') + '</button></div>').join('');
    }
    el.innerHTML = A.head(o.title || K.title) + '<div class="card" style="margin-top:12px">' + rows + '</div>' + files +
      '<div class="sheet-actions" style="margin-top:22px"><button class="btn btn-ghost" onclick="V.edit(\'' + kind + '\',\'' + jid + '\')">Edit</button><button class="btn btn-ghost btn-danger" onclick="V.del(\'' + kind + '\',\'' + jid + '\')">Delete</button></div>';
  }
  V.reveal = (kind, id, f) => {
    const k = id + ':' + f;
    if(V.shown[k]){ delete V.shown[k]; }
    else{ V.shown[k] = 1; setTimeout(() => { if(V.shown[k]){ delete V.shown[k]; if(A.cur === kind && A.sub === 'i:' + id && currentView === 'mod') A.renderMod(); } }, 15000); }
    A.renderMod(); V.touch();
  };
  V.copy = (kind, id, f) => {
    const o = V.data[kind][id]; if(!o || !o[f]) return;
    const secret = f === 'pass';
    A.copyText(o[f], secret ? 30000 : 0); A.toast(secret ? 'Copied - clears in 30s' : 'Copied'); V.touch();
  };
  V.del = (kind, id) => A.ask('Delete this ' + KINDS[kind].noun + '?', 'It is removed from every device. This cannot be undone.', 'Delete', () => {
    A.del(kind, id); delete V.data[kind][id]; delete V.refs[kind][id]; V.bad.delete(kind + ':' + id); A.sub = null; A.renderMod();
  }, true);

  /* ---------- attachments ---------- */
  V.wipeTmp = () => {
    try{ const P = root.Capacitor && root.Capacitor.Plugins; if(P && P.Filesystem) P.Filesystem.rmdir({ path:'vault-share', directory:'CACHE', recursive:true }).catch(() => {}); }catch(e){}
  };
  V.openFile = async (kind, id, i) => {
    const o = V.data[kind][id], f = o && o.files && o.files[i]; if(!f) return;
    V.touch();
    const cap = root.Capacitor, P = cap && cap.Plugins;
    try{
      if(cap && cap.isNativePlatform && cap.isNativePlatform() && P && P.Filesystem && P.Share){
        const b64 = f.data.slice(f.data.indexOf(',') + 1), name = (f.name || 'file').replace(/[^\w.\- ]/g, '_').slice(0, 80);
        const w = await P.Filesystem.writeFile({ path:'vault-share/' + name, data:b64, directory:'CACHE', recursive:true });
        await P.Share.share({ title:f.name, files:[w.uri] });
        setTimeout(V.wipeTmp, 120000);
        return;
      }
    }catch(e){ console.warn('share failed, falling back', e); }
    const bin = VC.unb64(f.data.slice(f.data.indexOf(',') + 1)), url = URL.createObjectURL(new Blob([bin], { type: f.type || 'application/octet-stream' }));
    const a = document.createElement('a'); a.href = url; a.download = f.name || 'file'; a.target = '_blank'; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  };

  const readDataURL = file => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = () => rej(r.error); r.readAsDataURL(file); });
  const loadImg = file => new Promise((res, rej) => {
    const u = URL.createObjectURL(file), im = new Image();
    im.onload = () => { URL.revokeObjectURL(u); res(im); }; im.onerror = () => { URL.revokeObjectURL(u); rej(new Error('image')); }; im.src = u;
  });
  async function shrink(file, room){
    const im = await loadImg(file), w0 = im.naturalWidth, h0 = im.naturalHeight;
    for(const [mx, q] of IMG_STEPS){
      const sc = Math.min(1, mx / Math.max(w0, h0)), c = document.createElement('canvas');
      c.width = Math.max(1, Math.round(w0 * sc)); c.height = Math.max(1, Math.round(h0 * sc));
      const g = c.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height); g.drawImage(im, 0, 0, c.width, c.height);
      const d = c.toDataURL('image/jpeg', q);
      if(d.length <= room) return d;
    }
    return null;
  }
  const used = () => V.draft.files.reduce((s, f) => s + f.data.length, 0);
  V.drawFiles = () => {
    const el = $('vFiles'); if(!el || !V.draft) return;
    el.innerHTML = V.draft.files.map((f, i) => '<div class="m-file"><span class="grow">' + E(f.name) + ' &middot; ' + kb(Math.round(f.data.length * 0.75)) + '</span><button type="button" class="row-x" aria-label="Remove file" onclick="V.rmFile(' + i + ')">&#10005;</button></div>').join('');
  };
  V.rmFile = i => { if(V.draft){ V.draft.files.splice(i, 1); V.drawFiles(); } };
  V.pick = async input => {
    const files = Array.from(input.files || []); input.value = '';
    if(!V.draft) return;
    for(const file of files){
      try{
        const room = FILE_BUDGET - used();
        let data, type = file.type || 'application/octet-stream';
        if(/^image\//.test(type)){ data = await shrink(file, room); type = 'image/jpeg'; if(!data){ A.toast('"' + file.name + '" is too big for this record - add it separately.'); continue; } }
        else{
          if(file.size > PDF_MAX_RAW){ A.toast('"' + file.name + '" is over 200 KB. Photos are shrunk automatically; other files must be smaller.'); continue; }
          data = await readDataURL(file); if(data.length > room){ A.toast('Not enough room left in this record for "' + file.name + '".'); continue; }
        }
        V.draft.files.push({ name:String(file.name || 'file').slice(0, 80), type, data });
      }catch(e){ console.error(e); A.toast('Could not read "' + file.name + '".'); }
    }
    V.drawFiles();
  };

  /* ---------- add / edit ---------- */
  V.pickCat = b => { if(!V.draft) return; V.draft.cat = b.dataset.c; document.querySelectorAll('#vCats .chip-opt').forEach(x => x.classList.toggle('sel', x === b)); };
  V.gen = id => { const e = $(id); if(!e) return; e.value = VC.generatePassword(20, { symbols:true }); e.type = 'text'; V.touch(); };
  V.edit = (kind, id) => {
    if(!V.key || V.busy) return;
    const K = KINDS[kind], o = id ? V.data[kind][id] : { title:'', cat:K.cats[0][0], notes:'', files:[] };
    if(!o) return;
    V.draft = { kind, id: id || null, cat: o.cat || K.cats[0][0], files: (o.files || []).map(f => Object.assign({}, f)) };
    let h = '<h3>' + (id ? 'Edit ' : 'New ') + K.noun + '</h3>' +
      '<div class="field"><label for="vf_title">Title</label><input id="vf_title" maxlength="120" value="' + E(o.title) + '"></div>' +
      '<div class="field"><label>Type</label><div class="chip-select" id="vCats">' + K.cats.map(c => '<button type="button" class="chip-opt ' + (c[0] === V.draft.cat ? 'sel' : '') + '" data-c="' + c[0] + '" onclick="V.pickCat(this)">' + c[1] + '</button>').join('') + '</div></div>';
    for(const [f, label, type] of K.fields){
      if(type === 'secret') h += '<div class="field"><label for="vf_' + f + '">' + label + '</label><div class="m-pw"><input id="vf_' + f + '" type="password" class="m-secret" autocomplete="off" maxlength="2000" value="' + E(o[f]) + '"><button type="button" class="m-iconbtn" aria-label="Show" onclick="V.toggleType(\'vf_' + f + '\')">' + A.icon('eye') + '</button><button type="button" class="m-iconbtn" aria-label="Generate a strong password" onclick="V.gen(\'vf_' + f + '\')">' + A.icon('dice') + '</button></div></div>';
      else h += '<div class="field"><label for="vf_' + f + '">' + label + '</label><input id="vf_' + f + '" type="' + (type === 'date' ? 'date' : 'text') + '" maxlength="300" value="' + E(o[f]) + '"></div>';
    }
    h += '<div class="field"><label for="vf_notes">Notes</label><textarea id="vf_notes" maxlength="4000">' + E(o.notes || '') + '</textarea></div>';
    if(K.files) h += '<div class="field"><label>Attachments</label><div id="vFiles"></div><label class="btn btn-ghost" style="display:inline-flex;gap:6px;align-items:center;cursor:pointer">' + A.icon('paperclip') + ' Add photo or PDF<input type="file" id="vFile" accept="image/*,application/pdf" multiple style="display:none" onchange="V.pick(this)"></label><div class="m-note">Photos are shrunk to fit. One record holds about 280 KB of attachments.</div></div>';
    h += '<div class="sheet-actions"><button class="btn btn-ghost" onclick="V.cancel()">Cancel</button><button class="btn btn-primary" id="vSave" onclick="V.saveForm()">Save</button></div>';
    openSheet(h); V.drawFiles(); V.touch();
  };
  V.cancel = () => { V.draft = null; closeSheet(); };
  V.saveForm = async () => {
    const d = V.draft; if(!d || !V.key) return;
    const K = KINDS[d.kind], o = { title: val('vf_title').slice(0, 120), cat: d.cat, notes: val('vf_notes').slice(0, 4000) };
    if(!o.title){ A.toast('Give it a title'); return; }
    for(const [f, , type] of K.fields){ const e = $('vf_' + f); const v = e ? (type === 'secret' ? e.value : e.value.trim()) : ''; if(v) o[f] = v; }
    if(K.files && d.files.length) o.files = d.files;
    if(JSON.stringify(o).length > PLAIN_MAX){ A.toast('This record is too large. Remove an attachment.'); return; }
    const b = $('vSave'); if(b) b.disabled = true;
    try{
      await saveRec(d.kind, d.id || A.uid(), o);
      V.draft = null; closeSheet(); A.renderMod(); V.touch();
    }catch(e){ console.error(e); A.toast('Could not save: ' + (e && e.message || e)); if(b) b.disabled = false; }
  };

  /* ---------- password change / reset ---------- */
  V.settings = () => openSheet('<h3>Vault password</h3>' +
    '<div class="m-note" style="margin-top:0">Changing the password re-encrypts every item. Sync your other devices first; afterwards they will ask for the new password.</div>' +
    '<div class="field"><label for="vcCur">Current password</label><input id="vcCur" type="password" autocomplete="current-password"></div>' +
    '<div class="field"><label for="vcNew">New password</label><input id="vcNew" type="password" autocomplete="new-password" oninput="V.meter(this.value)"></div><div class="m-meter"><i></i></div>' +
    '<div class="field"><label for="vcNew2">Repeat new password</label><input id="vcNew2" type="password" autocomplete="new-password"></div>' +
    '<div class="m-err" id="vErr" role="alert"></div>' +
    '<div class="sheet-actions"><button class="btn btn-ghost" onclick="closeSheet()">Cancel</button><button class="btn btn-primary" id="vcGo" onclick="V.changePw()">Change password</button></div>' +
    '<div class="m-note" style="margin-top:22px">Forgot it? The vault cannot be recovered. You can wipe it and start again.</div>' +
    '<button class="btn btn-ghost btn-danger btn-block" onclick="V.resetAsk()">Erase vault and start over</button>');

  V.changePw = async () => {
    const cur = ($('vcCur') || {}).value || '', n1 = ($('vcNew') || {}).value || '', n2 = ($('vcNew2') || {}).value || '';
    if(!V.key) return;
    if(V.bad.size){ err(V.bad.size + ' item(s) cannot be read on this device. Sync, then lock and unlock before changing the password.'); return; }
    if(n1.length < 10){ err('Use at least 10 characters.'); return; }
    if(n1 !== n2){ err('The new passwords do not match.'); return; }
    const b = $('vcGo'); if(b){ b.disabled = true; b.textContent = 'Re-encrypting...'; }
    V.busy = true;
    try{
      if(!await VC.unlock(cur, meta())){ err('Current password is wrong.'); return; }
      const r = await VC.createMeta(n1), sealed = {};
      for(const k of KIND_IDS) for(const [id, o] of Object.entries(V.data[k])) sealed[k + ':' + id] = await VC.seal(r.key, o, k + ':' + id);
      for(const [kid, rec] of Object.entries(sealed)){ const i = kid.indexOf(':'); DB.vault[kid.slice(0, i)][kid.slice(i + 1)] = rec; }
      DB.vault.vmeta = r.meta; V.key = r.key; V.metaSig = metaSig(r.meta);
      for(const k of KIND_IDS){ V.refs[k] = {}; for(const id of Object.keys(V.data[k])) V.refs[k][id] = DB.vault[k][id]; }
      save(); closeSheet(); A.toast('Password changed');
    }catch(e){ console.error(e); err('Failed: ' + (e && e.message || e)); }
    finally{ V.busy = false; const b2 = $('vcGo'); if(b2){ b2.disabled = false; b2.textContent = 'Change password'; } }
  };
  V.resetAsk = () => openSheet('<h3>Erase the vault?</h3><p class="muted" style="font-size:14px;line-height:1.5">This permanently deletes every health record, document and password from this device and from your Almanac server. It cannot be undone.</p>' +
    '<div class="field"><label for="vrTxt">Type DELETE to confirm</label><input id="vrTxt" autocomplete="off" autocapitalize="characters"></div>' +
    '<div class="sheet-actions"><button class="btn btn-ghost" onclick="closeSheet()">Cancel</button><button class="btn btn-primary btn-danger" onclick="V.reset()">Erase everything</button></div>');
  V.reset = () => {
    if(val('vrTxt') !== 'DELETE'){ A.toast('Type DELETE to confirm'); return; }
    for(const k of KIND_IDS) DB.vault[k] = {};
    DB.vault.vmeta = null; V.lock(); save(); closeSheet(); A.toast('Vault erased'); A.renderMod();
  };

  /* ---------- registration, sync + lifecycle hooks ---------- */
  function renderKind(kind, el, s){
    const K = KINDS[kind];
    if(A.isMember()){ el.innerHTML = A.head(K.title) + '<div class="m-note">Vaults are private to the Almanac owner.</div>'; return; }
    if(!secure()){ el.innerHTML = A.head(K.title) + '<div class="m-err">The vault needs a secure (HTTPS) connection and a current browser.</div>'; return; }
    if(!meta()) return setupView(kind, el);
    if(!V.key) return lockView(kind, el);
    V.touch();
    if(s && s.startsWith('i:')) return detail(kind, el, s.slice(2));
    listView(kind, el);
  }
  for(const k of KIND_IDS){
    A.reg({ id:k, title:KINDS[k].title, icon:KINDS[k].icon, desc:KINDS[k].desc, group:'vault',
      badge(){ return A.isMember() ? 'Owner only' : !meta() ? 'Not set up' : V.key ? 'Unlocked' : 'Locked'; },
      render(el, s){ renderKind(k, el, s); } });
  }
  V.lockNotice = false;
  A.on('afterSync', () => {
    const m = meta();
    if(V.key){
      if(!m || metaSig(m) !== V.metaSig){ V.lock(); A.toast('The vault password changed on another device. Unlock with the new one.'); return; }
      V.reload().then(() => { if(inVault() && !V.draft) A.renderMod(); });
    }else if(inVault()) A.renderMod();
  });
  document.addEventListener('visibilitychange', () => {
    if(document.hidden){ V.hiddenAt = Date.now(); return; }
    if(V.key && V.hiddenAt && Date.now() - V.hiddenAt > 60000) V.lock();
    V.hiddenAt = 0;
  });
  setInterval(() => { if(V.key && !V.busy && Date.now() - V.lastAct > 300000) V.lock(); }, 15000);
  ['pointerdown', 'keydown', 'touchstart'].forEach(ev => document.addEventListener(ev, () => { V.lastAct = Date.now(); }, { passive:true, capture:true }));
  A.on('boot', V.wipeTmp);
})(typeof window !== 'undefined' ? window : globalThis);
