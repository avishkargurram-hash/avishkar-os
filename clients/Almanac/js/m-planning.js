/* Almanac modules: Projects, Checklists (daily/weekly/monthly), Shopping (mine + family), Expenses & cashflow. */
(function(root){
  'use strict';
  const A = root.ALM, E = A.E, J = A.J, $ = A.$;
  const TICK = '<svg viewBox="0 0 24 24" fill="none"><path d="M5 12l5 5L19 7" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const box = (on, js) => '<button class="rem-check ' + (on ? 'done' : '') + '" aria-label="Toggle" onclick="' + js + '">' + TICK + '</button>';
  const pad = n => (n < 10 ? '0' : '') + n;
  const localDate = () => { const d = new Date(); return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); };
  const val = id => { const e = $(id); return e ? e.value.trim() : ''; };
  const clip = (s, n) => String(s || '').slice(0, n);
  const enterJs = js => 'onkeydown="if(event.key===\'Enter\'){event.preventDefault();' + js + '}"';

  /* ====================================================== PROJECTS ====================================================== */
  const P = root.P = {};
  const PSTAT = { active:'Active', hold:'On hold', done:'Done' };
  const prog = p => {
    const all = (p.milestones || []).concat(p.tasks || []), d = all.filter(x => x.done).length;
    return { d, n: all.length, pct: all.length ? Math.round(100 * d / all.length) : 0 };
  };
  const overdue = (due, status) => !!due && status !== 'done' && due < localDate();

  function prjList(el){
    const list = A.list('prj').sort((a, b) => (a.status === 'done') - (b.status === 'done') ||
      (a.due || '9999').localeCompare(b.due || '9999') || (a.name || '').localeCompare(b.name || ''));
    let h = A.head('Projects', { add:'P.add()', addLabel:'New project', sub:'Milestones, tasks and where each one stands.' });
    if(!list.length) h += '<div class="card" style="margin-top:14px"><div class="empty">No projects yet. Tap + to start one.</div></div>';
    for(const p of list){
      const g = prog(p), od = overdue(p.due, p.status);
      h += '<button class="card m-card" style="margin-top:12px" onclick="ALM.sub_(\'p:' + J(p.id) + '\')"><div class="top"><div class="grow"><h4>' + E(p.name || 'Untitled') + '</h4>' +
        '<div class="meta">' + (p.due ? 'Due ' + E(A.fdate(p.due)) : 'No due date') + ' &middot; ' + g.d + '/' + g.n + ' done</div></div>' +
        '<span class="m-badge ' + (p.status === 'done' ? '' : p.status === 'hold' ? 'grey' : 'gold') + '">' + E(PSTAT[p.status] || 'Active') + '</span>' +
        (od ? '<span class="m-badge bad">Overdue</span>' : '') + '</div>' +
        '<div class="m-bar ' + (od ? 'bad' : '') + '"><i style="width:' + g.pct + '%"></i></div></button>';
    }
    el.innerHTML = h;
  }

  function prjDetail(el, id){
    const p = A.get('prj', id);
    if(!p){ A.sub = null; return prjList(el); }
    const g = prog(p), jid = J(id);
    const rows = (kind, arr, isM) => (arr || []).map(x =>
      '<div class="m-item ' + (x.done ? 'done' : '') + '">' + box(x.done, "P.toggle('" + jid + "','" + kind + "','" + J(x.id) + "')") +
      '<div class="grow"><b>' + E(x.title) + '</b>' + (isM && x.due ? '<div class="sub">' + (overdue(x.due, x.done ? 'done' : 'active') ? 'Overdue &middot; ' : '') + E(A.fdate(x.due)) + '</div>' : '') + '</div>' +
      '<button class="row-x" aria-label="Remove" onclick="P.rmItem(\'' + jid + '\',\'' + kind + '\',\'' + J(x.id) + '\')">&#10005;</button></div>').join('') ||
      '<div class="empty" style="padding:16px">None yet.</div>';
    let h = A.head(p.name || 'Project') +
      '<div class="m-sub">' + (p.due ? 'Due ' + E(A.fdate(p.due)) + ' &middot; ' : '') + g.d + ' of ' + g.n + ' done</div>' +
      '<div class="m-bar" style="margin:10px 2px 14px"><i style="width:' + g.pct + '%"></i></div>' +
      '<div class="chip-select" style="margin-bottom:6px">' + Object.keys(PSTAT).map(s =>
        '<button class="chip-opt ' + (p.status === s || (!p.status && s === 'active') ? 'sel' : '') + '" onclick="P.setStatus(\'' + jid + '\',\'' + s + '\')">' + PSTAT[s] + '</button>').join('') + '</div>' +
      (p.notes ? '<div class="m-note">' + E(p.notes) + '</div>' : '') +
      '<div class="section-title">Milestones</div><div class="card">' + rows('milestones', p.milestones, true) +
      '<div class="m-add-inline"><input id="pmMs" maxlength="120" placeholder="New milestone" ' + enterJs("P.addItem('" + jid + "','milestones')") + '>' +
      '<input id="pmMsDue" type="date" style="flex:none;width:136px" aria-label="Milestone due date"><button onclick="P.addItem(\'' + jid + '\',\'milestones\')">Add</button></div></div>' +
      '<div class="section-title">Tasks</div><div class="card">' + rows('tasks', p.tasks, false) +
      '<div class="m-add-inline"><input id="pmTk" maxlength="160" placeholder="New task" ' + enterJs("P.addItem('" + jid + "','tasks')") + '><button onclick="P.addItem(\'' + jid + '\',\'tasks\')">Add</button></div></div>' +
      '<div class="sheet-actions" style="margin-top:22px"><button class="btn btn-ghost" onclick="P.edit(\'' + jid + '\')">Edit details</button>' +
      '<button class="btn btn-ghost btn-danger" onclick="P.del(\'' + jid + '\')">Delete</button></div>';
    el.innerHTML = h;
  }

  P.add = () => P.edit(null);
  P.edit = id => {
    const p = id ? A.get('prj', id) : { name:'', due:'', status:'active', notes:'' };
    if(!p) return;
    openSheet('<h3>' + (id ? 'Edit project' : 'New project') + '</h3>' +
      '<div class="field"><label for="pjName">Name</label><input id="pjName" maxlength="100" value="' + E(p.name) + '"></div>' +
      '<div class="field-row"><div class="field"><label for="pjDue">Due date</label><input id="pjDue" type="date" value="' + E(p.due || '') + '"></div></div>' +
      '<div class="field"><label for="pjNotes">Notes</label><textarea id="pjNotes" maxlength="1000">' + E(p.notes || '') + '</textarea></div>' +
      '<div class="sheet-actions"><button class="btn btn-ghost" onclick="closeSheet()">Cancel</button><button class="btn btn-primary" onclick="P.save(' + (id ? "'" + J(id) + "'" : 'null') + ')">Save</button></div>');
  };
  P.save = id => {
    const name = clip(val('pjName'), 100);
    if(!name){ A.toast('Give the project a name'); return; }
    const p = id ? Object.assign({}, A.get('prj', id)) : { status:'active', milestones:[], tasks:[] };
    p.name = name; p.due = val('pjDue') || ''; p.notes = clip(val('pjNotes'), 1000);
    A.put('prj', id || A.uid(), p); closeSheet(); A.renderMod();
  };
  P.setStatus = (id, s) => { const p = A.get('prj', id); if(!p || !PSTAT[s]) return; A.put('prj', id, Object.assign({}, p, { status:s })); A.renderMod(); };
  P.toggle = (id, kind, iid) => {
    const p = A.get('prj', id); if(!p) return;
    const q = Object.assign({}, p); q[kind] = (p[kind] || []).map(x => x.id === iid ? Object.assign({}, x, { done: !x.done }) : x);
    A.put('prj', id, q); A.renderMod();
  };
  P.rmItem = (id, kind, iid) => {
    const p = A.get('prj', id); if(!p) return;
    const q = Object.assign({}, p); q[kind] = (p[kind] || []).filter(x => x.id !== iid);
    A.put('prj', id, q); A.renderMod();
  };
  P.addItem = (id, kind) => {
    const p = A.get('prj', id); if(!p) return;
    const t = clip(val(kind === 'tasks' ? 'pmTk' : 'pmMs'), kind === 'tasks' ? 160 : 120);
    if(!t) return;
    if((p[kind] || []).length >= 200){ A.toast('That list is full'); return; }
    const it = { id: A.uid(), title: t, done: false };
    if(kind === 'milestones'){ const d = val('pmMsDue'); if(d) it.due = d; }
    const q = Object.assign({}, p); q[kind] = (p[kind] || []).concat([it]);
    A.put('prj', id, q); A.renderMod();
    const f = $(kind === 'tasks' ? 'pmTk' : 'pmMs'); if(f) f.focus();
  };
  P.del = id => A.ask('Delete project?', 'This removes the project, its milestones and tasks on every device.', 'Delete', () => { A.del('prj', id); A.sub = null; A.renderMod(); }, true);

  A.reg({ id:'prj', title:'Projects', icon:'folder', desc:'Milestones & tasks', group:'plan',
    badge(){ const n = A.list('prj').filter(p => p.status !== 'done').length; return n ? n + ' active' : 'Milestones & tasks'; },
    chip(){ const l = A.list('prj').filter(p => p.status !== 'done'); if(!l.length) return null; const od = l.filter(p => overdue(p.due, p.status)).length; return { k:'Projects', v: l.length + ' active' + (od ? ' · ' + od + ' late' : '') }; },
    render(el, sub){ sub && sub.startsWith('p:') ? prjDetail(el, sub.slice(2)) : prjList(el); } });

  /* ====================================================== CHECKLISTS ====================================================== */
  const CL = root.CL = {};
  let clTier = 'daily';
  const TIERS = { daily:['Daily','today'], weekly:['Weekly','this week'], monthly:['Monthly','this month'] };
  const doneIds = c => { const d = c.done && c.done[A.periodKey(c.tier)]; return Array.isArray(d) ? d : []; };

  function clList(el){
    const lists = A.list('chk').filter(c => (c.tier || 'daily') === clTier).sort((a, b) => (a.title || '').localeCompare(b.title || ''));
    let h = A.head('Checklists', { add:'CL.add()', addLabel:'New checklist', sub:'Resets itself each day, week or month.' }) +
      '<div class="segment">' + Object.keys(TIERS).map(t => '<button class="' + (t === clTier ? 'active' : '') + '" onclick="CL.tier(\'' + t + '\')">' + TIERS[t][0] + '</button>').join('') + '</div>';
    if(!lists.length) h += '<div class="card" style="margin-top:14px"><div class="empty">No ' + TIERS[clTier][0].toLowerCase() + ' checklists. Tap + to make one.</div></div>';
    for(const c of lists){
      const items = c.items || [], ids = new Set(doneIds(c)), got = items.filter(i => ids.has(i.id)).length, pct = items.length ? Math.round(100 * got / items.length) : 0;
      h += '<button class="card m-card" style="margin-top:12px" onclick="ALM.sub_(\'c:' + J(c.id) + '\')"><div class="top"><div class="grow"><h4>' + E(c.title || 'Untitled') + '</h4>' +
        '<div class="meta">' + got + ' of ' + items.length + ' ' + TIERS[clTier][1] + '</div></div>' +
        (items.length && got === items.length ? '<span class="m-badge">All done</span>' : '') + '</div><div class="m-bar"><i style="width:' + pct + '%"></i></div></button>';
    }
    el.innerHTML = h;
  }
  function clDetail(el, id){
    const c = A.get('chk', id);
    if(!c){ A.sub = null; return clList(el); }
    const jid = J(id), items = c.items || [], ids = new Set(doneIds(c)), got = items.filter(i => ids.has(i.id)).length;
    el.innerHTML = A.head(c.title || 'Checklist') +
      '<div class="m-sub">' + TIERS[c.tier || 'daily'][0] + ' &middot; ' + got + ' of ' + items.length + ' ' + TIERS[c.tier || 'daily'][1] + '</div>' +
      '<div class="card" style="margin-top:12px">' + (items.map(i =>
        '<div class="m-item ' + (ids.has(i.id) ? 'done' : '') + '">' + box(ids.has(i.id), "CL.toggle('" + jid + "','" + J(i.id) + "')") + '<div class="grow"><b>' + E(i.t) + '</b></div>' +
        '<button class="row-x" aria-label="Remove" onclick="CL.rmItem(\'' + jid + '\',\'' + J(i.id) + '\')">&#10005;</button></div>').join('') ||
        '<div class="empty" style="padding:16px">Add the first item below.</div>') +
      '<div class="m-add-inline"><input id="clNew" maxlength="120" placeholder="New item" ' + enterJs("CL.addItem('" + jid + "')") + '><button onclick="CL.addItem(\'' + jid + '\')">Add</button></div></div>' +
      '<div class="sheet-actions" style="margin-top:22px"><button class="btn btn-ghost" onclick="CL.edit(\'' + jid + '\')">Rename / change cycle</button>' +
      '<button class="btn btn-ghost btn-danger" onclick="CL.del(\'' + jid + '\')">Delete</button></div>';
  }
  CL.tier = t => { if(TIERS[t]){ clTier = t; A.renderMod(); } };
  CL.add = () => CL.edit(null);
  let editTier = 'daily';
  CL.pick = t => { editTier = t; document.querySelectorAll('#clTiers .chip-opt').forEach(b => b.classList.toggle('sel', b.dataset.t === t)); };
  CL.edit = id => {
    const c = id ? A.get('chk', id) : { title:'', tier: clTier };
    if(!c) return;
    editTier = c.tier || 'daily';
    openSheet('<h3>' + (id ? 'Edit checklist' : 'New checklist') + '</h3>' +
      '<div class="field"><label for="clTitle">Title</label><input id="clTitle" maxlength="80" value="' + E(c.title) + '"></div>' +
      '<div class="field"><label>Resets</label><div class="chip-select" id="clTiers">' + Object.keys(TIERS).map(t =>
        '<button class="chip-opt ' + (t === editTier ? 'sel' : '') + '" data-t="' + t + '" onclick="CL.pick(\'' + t + '\')">' + TIERS[t][0] + '</button>').join('') + '</div></div>' +
      '<div class="sheet-actions"><button class="btn btn-ghost" onclick="closeSheet()">Cancel</button><button class="btn btn-primary" onclick="CL.save(' + (id ? "'" + J(id) + "'" : 'null') + ')">Save</button></div>');
  };
  CL.save = id => {
    const title = clip(val('clTitle'), 80);
    if(!title){ A.toast('Give the checklist a title'); return; }
    const c = id ? Object.assign({}, A.get('chk', id)) : { items:[], done:{} };
    c.title = title; c.tier = editTier;
    A.put('chk', id || A.uid(), c); clTier = c.tier; closeSheet(); A.renderMod();
  };
  CL.toggle = (id, iid) => {
    const c = A.get('chk', id); if(!c) return;
    const k = A.periodKey(c.tier || 'daily'), done = Object.assign({}, c.done || {}), cur = new Set(done[k] || []);
    cur.has(iid) ? cur.delete(iid) : cur.add(iid);
    done[k] = Array.from(cur);
    const keys = Object.keys(done).sort().reverse();
    keys.slice(40).forEach(x => delete done[x]);
    A.put('chk', id, Object.assign({}, c, { done })); A.renderMod();
  };
  CL.addItem = id => {
    const c = A.get('chk', id), t = clip(val('clNew'), 120); if(!c || !t) return;
    if((c.items || []).length >= 100){ A.toast('That checklist is full'); return; }
    A.put('chk', id, Object.assign({}, c, { items: (c.items || []).concat([{ id: A.uid(), t }]) })); A.renderMod();
    const f = $('clNew'); if(f) f.focus();
  };
  CL.rmItem = (id, iid) => { const c = A.get('chk', id); if(!c) return; A.put('chk', id, Object.assign({}, c, { items: (c.items || []).filter(i => i.id !== iid) })); A.renderMod(); };
  CL.del = id => A.ask('Delete checklist?', 'This removes the checklist on every device.', 'Delete', () => { A.del('chk', id); A.sub = null; A.renderMod(); }, true);

  A.reg({ id:'chk', title:'Checklists', icon:'list', desc:'Daily, weekly, monthly', group:'plan',
    chip(){
      const l = A.list('chk').filter(c => (c.tier || 'daily') === 'daily' && (c.items || []).length); if(!l.length) return null;
      let got = 0, n = 0; l.forEach(c => { const s = new Set(doneIds(c)); n += c.items.length; got += c.items.filter(i => s.has(i.id)).length; });
      return { k:'Daily checklists', v: got + '/' + n + ' done' };
    },
    render(el, sub){ sub && sub.startsWith('c:') ? clDetail(el, sub.slice(2)) : clList(el); } });

  /* ====================================================== SHOPPING ====================================================== */
  const SH = root.SH = {};
  let shTab = 'mine';
  const shKind = () => (A.isMember() || shTab === 'family') ? 'fshop' : 'shop';
  function shopRender(el){
    const k = shKind(), fam = k === 'fshop';
    const list = A.list(k).sort((a, b) => (!!a.done - !!b.done) || (a.name || '').localeCompare(b.name || ''));
    const nDone = list.filter(i => i.done).length;
    let h = A.head('Shopping', { sub: fam ? 'Shared with your family.' : 'Your own list.' });
    if(!A.isMember()) h += '<div class="segment"><button class="' + (!fam ? 'active' : '') + '" onclick="SH.tab(\'mine\')">Mine</button><button class="' + (fam ? 'active' : '') + '" onclick="SH.tab(\'family\')">Family</button></div>';
    h += '<div class="card" style="margin-top:14px">' + (list.map(i =>
      '<div class="m-item ' + (i.done ? 'done' : '') + '">' + box(i.done, "SH.toggle('" + J(i.id) + "')") + '<div class="grow"><b>' + E(i.name) + (i.qty ? '<span class="m-badge grey">' + E(i.qty) + '</span>' : '') + '</b>' +
      (fam && i.by ? '<div class="sub">added by ' + E(i.by) + '</div>' : '') + '</div>' +
      '<button class="row-x" aria-label="Remove" onclick="SH.rm(\'' + J(i.id) + '\')">&#10005;</button></div>').join('') || '<div class="empty">Nothing on the list.</div>') +
      '<div class="m-add-inline"><input id="shName" maxlength="80" placeholder="Add an item" ' + enterJs('SH.add()') + '><input id="shQty" maxlength="8" placeholder="Qty" style="flex:none;width:64px"><button onclick="SH.add()">Add</button></div></div>';
    if(nDone) h += '<div style="text-align:center;margin-top:14px"><button class="btn btn-ghost" onclick="SH.clearDone()">Clear ' + nDone + ' bought</button></div>';
    el.innerHTML = h;
  }
  SH.tab = t => { shTab = t === 'family' ? 'family' : 'mine'; A.renderMod(); };
  SH.add = () => {
    const name = clip(val('shName'), 80); if(!name) return;
    const k = shKind(), rec = { name, qty: clip(val('shQty'), 8), done: false };
    if(k === 'fshop'){ const me = A.famMe ? A.famMe() : null; rec.by = clip(me && me.name || '', 40); }
    A.put(k, A.uid(), rec); A.renderMod();
    const f = $('shName'); if(f) f.focus();
  };
  SH.toggle = id => { const k = shKind(), r = A.get(k, id); if(!r) return; A.put(k, id, Object.assign({}, r, { done: !r.done })); A.renderMod(); };
  SH.rm = id => { A.del(shKind(), id); A.renderMod(); };
  SH.clearDone = () => { const k = shKind(); A.list(k).filter(i => i.done).forEach(i => delete A.store(k)[i.id]); save(); A.renderMod(); };

  A.reg({ id:'shop', title:'Shopping', icon:'cart', desc:'Mine & family list', group:'plan', member:true,
    badge(){ const n = A.list('shop').filter(i => !i.done).length; return n ? n + ' to buy' : 'Mine & family list'; },
    chip(){ const n = A.list('shop').filter(i => !i.done).length + A.list('fshop').filter(i => !i.done).length; return n ? { k:'Shopping', v: n + ' to buy' } : null; },
    render: shopRender });

  /* ====================================================== EXPENSES ====================================================== */
  const EX = root.EX = {};
  let exMonth = localDate().slice(0, 7), exType = 'out';
  const CATS = { out:['Food','Transport','Bills','Shopping','Health','Fun','Other'], in:['Salary','Refund','Gift','Other'] };
  const num = v => (typeof v === 'number' && isFinite(v)) ? v : 0;
  const shiftMonth = (m, d) => { let y = +m.slice(0, 4), mo = +m.slice(5, 7) - 1 + d; y += Math.floor(mo / 12); mo = ((mo % 12) + 12) % 12; return y + '-' + pad(mo + 1); };

  function exRender(el){
    const all = A.list('exp').filter(e => String(e.date || '').startsWith(exMonth));
    let inc = 0, out = 0; const cats = {};
    all.forEach(e => { const a = num(e.amt); if(e.type === 'in') inc += a; else { out += a; const c = e.cat || 'Other'; cats[c] = (cats[c] || 0) + a; } });
    const top = Object.entries(cats).sort((a, b) => b[1] - a[1]), max = top.length ? top[0][1] : 1;
    const rows = all.sort((a, b) => String(b.date).localeCompare(String(a.date)) || (b.id > a.id ? 1 : -1));
    const lbl = A.MON[+exMonth.slice(5, 7) - 1] + ' ' + exMonth.slice(0, 4);
    let h = A.head('Expenses', { add:'EX.edit(null)', addLabel:'Add entry', sub:'Spending and income. Amounts in rupees.' }) +
      '<div class="m-month"><button class="m-iconbtn" aria-label="Previous month" onclick="EX.month(-1)">' + A.icon('back') + '</button><b>' + lbl + '</b>' +
      '<button class="m-iconbtn" aria-label="Next month" style="transform:rotate(180deg)" onclick="EX.month(1)">' + A.icon('back') + '</button></div>' +
      '<div class="m-money"><div class="in"><small>Earned</small><b>' + A.money(inc) + '</b></div><div class="out"><small>Spent</small><b>' + A.money(out) + '</b></div><div><small>Net</small><b>' + A.money(inc - out, true) + '</b></div></div>';
    if(top.length) h += '<div class="section-title">Where it went</div><div class="card" style="padding:10px 16px">' + top.slice(0, 6).map(([c, a]) =>
      '<div class="m-cat"><span class="nm">' + E(c) + '</span><div class="m-bar"><i style="width:' + Math.max(3, Math.round(100 * a / max)) + '%"></i></div><span class="am">' + A.money(a) + '</span></div>').join('') + '</div>';
    h += '<div class="section-title">Entries</div><div class="card">' + (rows.map(e =>
      '<button class="m-item" onclick="EX.edit(\'' + J(e.id) + '\')"><div class="grow"><b>' + E(e.cat || 'Other') + '</b><div class="sub">' + E(A.fdate(e.date)) + (e.note ? ' &middot; ' + E(e.note) : '') + '</div></div>' +
      '<span class="m-amt ' + (e.type === 'in' ? 'm-amt-in' : 'm-amt-out') + '">' + (e.type === 'in' ? '+' : '-') + A.money(num(e.amt)).replace('-', '') + '</span></button>').join('') ||
      '<div class="empty">No entries this month.</div>') + '</div>';
    el.innerHTML = h;
  }
  EX.month = d => { exMonth = shiftMonth(exMonth, d); A.renderMod(); };
  EX.type = t => { exType = t; document.querySelectorAll('#exType .chip-opt').forEach(b => b.classList.toggle('sel', b.dataset.t === t)); EX.cats(); };
  EX.cats = () => { const el = $('exCats'); if(el) el.innerHTML = CATS[exType].map(c => '<button class="chip-opt" onclick="EX.pickCat(this)">' + c + '</button>').join(''); };
  EX.pickCat = b => { $('exCat').value = b.textContent; };
  EX.edit = id => {
    const e = id ? A.get('exp', id) : { type: exType, amt:'', cat:'', note:'', date: localDate() };
    if(!e) return;
    exType = e.type === 'in' ? 'in' : 'out';
    openSheet('<h3>' + (id ? 'Edit entry' : 'New entry') + '</h3>' +
      '<div class="chip-select" id="exType" style="margin-bottom:12px"><button class="chip-opt ' + (exType === 'out' ? 'sel' : '') + '" data-t="out" onclick="EX.type(\'out\')">Spent</button><button class="chip-opt ' + (exType === 'in' ? 'sel' : '') + '" data-t="in" onclick="EX.type(\'in\')">Earned</button></div>' +
      '<div class="field-row"><div class="field"><label for="exAmt">Amount (₹)</label><input id="exAmt" type="number" inputmode="decimal" min="0" step="0.01" value="' + E(e.amt) + '"></div>' +
      '<div class="field"><label for="exDate">Date</label><input id="exDate" type="date" value="' + E(e.date) + '"></div></div>' +
      '<div class="field"><label for="exCat">Category</label><input id="exCat" maxlength="24" value="' + E(e.cat) + '"></div><div class="chip-select" id="exCats" style="margin:-4px 0 12px"></div>' +
      '<div class="field"><label for="exNote">Note (optional)</label><input id="exNote" maxlength="120" value="' + E(e.note) + '"></div>' +
      '<div class="sheet-actions">' + (id ? '<button class="btn btn-ghost btn-danger" onclick="EX.del(\'' + J(id) + '\')">Delete</button>' : '<button class="btn btn-ghost" onclick="closeSheet()">Cancel</button>') +
      '<button class="btn btn-primary" onclick="EX.save(' + (id ? "'" + J(id) + "'" : 'null') + ')">Save</button></div>');
    EX.cats();
  };
  EX.save = id => {
    const amt = Math.round(parseFloat(val('exAmt')) * 100) / 100, date = val('exDate');
    if(!(amt > 0) || amt >= 1e9){ A.toast('Enter an amount above zero'); return; }
    if(!/^\d{4}-\d{2}-\d{2}$/.test(date)){ A.toast('Pick a date'); return; }
    A.put('exp', id || A.uid(), { type: exType, amt, cat: clip(val('exCat'), 24) || 'Other', note: clip(val('exNote'), 120), date });
    exMonth = date.slice(0, 7); closeSheet(); A.renderMod();
  };
  EX.del = id => { A.del('exp', id); closeSheet(); A.renderMod(); };

  A.reg({ id:'exp', title:'Expenses', icon:'wallet', desc:'Spending & cashflow', group:'plan',
    badge(){ const m = localDate().slice(0, 7); let n = 0; A.list('exp').forEach(e => { if(String(e.date).startsWith(m)) n += (e.type === 'in' ? 1 : -1) * num(e.amt); }); return A.list('exp').length ? 'Net ' + A.money(n, true) + ' this month' : 'Spending & cashflow'; },
    chip(){ const m = localDate().slice(0, 7); let o = 0, any = false; A.list('exp').forEach(e => { if(String(e.date).startsWith(m)){ any = true; if(e.type !== 'in') o += num(e.amt); } }); return any ? { k:'Spent this month', v: A.money(o) } : null; },
    render: exRender });
})(typeof window !== 'undefined' ? window : globalThis);
