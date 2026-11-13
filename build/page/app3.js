
// ---------- search boxes, suggestions and tags ----------
function drugKey() {
  const q = $('di').value.trim(), dd = $('dd');
  if (q.length < 2) { dd.classList.remove('show'); return; }
  const ranked = rankDrugs(q, 40), taken = {}; ranked.forEach(g => { taken[g.key] = 1; });
  const shown = shownCodes(ranked.map(g => g.items));
  const mb = rankPBD(q, 30).filter(x => !shown.has(x.code)), bs = biosimHits(q, taken);
  if (!ranked.length && !mb.length && !bs.length) { dd.innerHTML = '<div class="ml-note">No matches</div>'; dd.classList.add('show'); return; }
  let h = '';
  if (ranked.some(g => g.fuzzy)) h += '<div class="ml-note warn">No exact match. Closest spellings:</div>';
  h += ranked.map(g => {
    const ex = g.items[0];
    return '<div class="ml-item" data-act="drug" data-key="' + esc(g.key) + '"><div class="main">' + esc(g.key) + (g.fuzzy ? ' <span class="dym">did you mean?</span>' : '') +
      ' <span class="cnt">(' + g.items.length + ')</span></div><div class="sub">' + esc(ex.s || '') + ' · ' + esc(ex.f || '') + (ex.h ? ' · ' + esc(ex.h) : '') + '</div></div>';
  }).join('');
  h += mb.map(x => '<div class="ml-item" data-act="med" data-key="' + esc(x.code) + '"><div class="main">' + esc(x.e.n) + ' <span class="cnt">(' + esc(x.code) + ')</span></div><div class="sub med">' +
    esc(medSub(x.code, x.e)) + '</div></div>').join('');
  h += bs.slice(0, 10).map(b => '<div class="ml-item" data-act="bs" data-key="' + esc(b.code) + '"><div class="main">' + esc(b.b || b.g || b.code) + ' <span class="cnt">(' + esc(b.code) + ')</span></div><div class="sub med">Biosimilar · ' + esc(b.g || '') + '</div></div>').join('');
  dd.innerHTML = h; dd.classList.add('show');
}
function planKey() {
  const q = $('pi').value.trim(), dd = $('pd');
  if (q.length < 2) { dd.classList.remove('show'); return; }
  const groups = {};
  Y.P.forEach(p => { if (fuzzyMatch(q, p.pn || '', p.cn || '', p.cid || '')) { const k = p.cn || p.cid; (groups[k] = groups[k] || []).push(p); } });
  const keys = Object.keys(groups).sort().slice(0, 30);
  if (!keys.length) { dd.innerHTML = '<div class="ml-note">No matches</div>'; dd.classList.add('show'); return; }
  const total = keys.reduce((n, k) => n + groups[k].length, 0);
  let h = '<div class="ml-item" data-act="planq" data-key="' + esc(q) + '"><div class="main all">All matches <span class="cnt">(' + total + ' plans across ' + keys.length + ' organizations)</span></div><div class="sub">Select every plan matching “' + esc(q) + '”</div></div>';
  h += keys.map(k => {
    const pr = groups[k].map(p => parseFloat(p.pr) || 0);
    return '<div class="ml-item" data-act="plan" data-key="' + esc(k) + '"><div class="main">' + esc(k) + ' <span class="cnt">(' + groups[k].length + ')</span></div><div class="sub">$' + Math.min(...pr).toFixed(0) + '–$' + Math.max(...pr).toFixed(0) + '/mo premium</div></div>';
  }).join('');
  dd.innerHTML = h; dd.classList.add('show');
}
function addDrug(act, key) {
  $('dd').classList.remove('show'); $('di').value = '';
  if (exampleShown) { selDrugs = []; exampleShown = false; }
  let sel;
  if (act === 'drug') sel = { key, rxcuis: DL.filter(d => dkey(d) === key).map(d => d.r) };
  else if (act === 'med') sel = { key: medName(key), rxcuis: [medRx(key)], mb: 1 };
  else { const b = G.BIOSIM[key]; sel = { key: b.b || b.g || key, rxcuis: [bsRx(key)], bs: 1 }; }
  if (!selDrugs.find(s => s.key === sel.key)) selDrugs.push(sel);
  renderTags();
}
function addIng(items, focus) {               // from the "Same ingredient" row: add products to the comparison and keep what is selected
  exampleShown = false;
  const was = $('covSelect') ? $('covSelect').value : '';
  let last = '';
  items.slice(0, 40).forEach(it => {
    const key = it.kind === 'drug' ? it.key : medName(it.key);
    if (!selDrugs.find(s => s.key === key)) selDrugs.push(it.kind === 'drug' ? { key, rxcuis: DL.filter(d => dkey(d) === key).map(d => d.r) } : { key, rxcuis: [medRx(it.key)], mb: 1 });
    last = key;
  });
  renderTags(); search(true);
  const want = focus ? last : was, sel = $('covSelect');
  if (sel && want && COVB[want]) { sel.value = want; showCov(want); }
}
function addPlan(act, key) {
  $('pd').classList.remove('show'); $('pi').value = '';
  if (!selPlans.find(s => s.key === key)) selPlans.push({ key, q: act === 'planq' });
  renderTags();
}
function renderTags() {
  const tag = (cls, label, kind, i) => '<span class="tag ' + cls + '">' + esc(label) + ' <button type="button" class="x" data-act="rem" data-kind="' + kind + '" data-i="' + i + '" aria-label="Remove ' + esc(label) + '">×</button></span>';
  $('dt').innerHTML = selDrugs.map((s, i) => tag('tag-drug', s.mb ? s.key : s.key + ' (' + s.rxcuis.length + ')', 'd', i)).join('');
  $('pt').innerHTML = selPlans.map((s, i) => tag('tag-plan', s.key + ' (' + planMatches(s).length + ')', 'p', i)).join('');
  $('stags').innerHTML = selStates.map((s, i) => tag('tag-state', s, 's', i)).join('');
  $('mtags').innerHTML = selMT.map((s, i) => tag('tag-drug', s, 'm', i)).join('');
}
function clearAll() {
  selDrugs = []; selPlans = []; selStates = ['NY']; selMT = []; ROWS = []; exampleShown = false;
  ['di', 'pi'].forEach(i => { $(i).value = ''; });
  renderTags();
  $('summary').innerHTML = ''; $('covpanel').innerHTML = '';
  $('results').innerHTML = '<div class="empty">Type a drug name, a plan name, or both, then press Search.<br>The state filter starts on New York.</div>';
}
function runExample() {
  const g = rankDrugs(G.META.example || 'ELIQUIS', 1)[0];
  if (!g) return;
  selDrugs = [{ key: g.key, rxcuis: g.items.map(d => d.r) }];
  exampleShown = true; renderTags(); search(true);
}
