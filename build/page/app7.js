
// ---------- results table ----------
const COLS = ['Drug', 'Strength / form', 'Plan', 'Type', 'State', 'Tier', 'Cost share (30 days)', 'Prior auth', 'Step therapy', 'Qty limit', 'HCPCS', 'NY Medicaid'];
function nyCell(r) {
  const v = G.NYMC[r.rx];
  return v === 'Y' ? '<span class="pill ok">Preferred</span>' : v === 'N' ? '<span class="pill warn">Non-Preferred</span>' : v === 'X' ? '<span class="pill ok">Covered</span>' : r.d.h ? '<span class="mut">Medical benefit</span>' : '<span class="mut">—</span>';
}
function renderTable() {
  const el = $('results');
  if (!ROWS.length) { el.innerHTML = '<div class="empty">Nothing matched. Remove a filter or try another spelling.</div>'; return; }
  const head = '<tr>' + COLS.map((c, i) => '<th scope="col"><button type="button" data-act="sort" data-i="' + i + '">' + c + (sortCol === i ? (sortAsc ? ' ▲' : ' ▼') : '') + '</button></th>').join('') + '</tr>';
  const out = [];
  for (const r of ROWS) {
    const d = r.d, hc = d.h ? '<span class="code">' + esc(d.h) + '</span>' : '<span class="mut">—</span>';
    const drug = '<td><strong>' + esc(d.b || '(generic)') + '</strong>' + (r.cv && r.cv.sel === 'Y' ? ' <span class="pill neg" title="Selected drug under the Medicare Drug Price Negotiation Program">Negotiated</span>' : '') + '</td><td class="sm">' + esc(d.s || '') + (d.f ? ' · ' + esc(d.f) : '') + '</td>';
    if (!r.p) { out.push('<tr class="nc">' + drug + '<td colspan="8" class="mid">Medical-benefit product: not on pharmacy formularies. See the coverage summary.</td><td>' + hc + '</td><td>' + nyCell(r) + '</td></tr>'); continue; }
    const plan = '<td>' + esc(r.p.pn) + '<div class="sub">' + esc(r.p.cn) + '</div></td><td><span class="pill type">' + esc(r.p.pt || r.p.mt) + '</span></td><td class="sm">' + r.p.sa.slice(0, 3).join(', ') + (r.p.sa.length > 3 ? ' +' + (r.p.sa.length - 3) : '') + '</td>';
    if (!r.cv) { out.push('<tr class="nc">' + drug + plan + '<td colspan="5" class="mid nof">Not on formulary</td><td>' + hc + '</td><td>' + nyCell(r) + '</td></tr>'); continue; }
    const cv = r.cv, t = parseInt(cv.tier) <= 6 ? cv.tier : '3';
    out.push('<tr>' + drug + plan + '<td><span class="tier t' + t + '" title="' + esc(tl(cv.tier)) + '">Tier ' + esc(cv.tier) + '</span></td><td class="num">' + getCost(r.p, cv, r.rx).html + '</td><td>' + yn(cv.pa) + '</td><td>' + yn(cv.st) + '</td><td class="sm">' +
      (cv.ql === 'Y' ? esc(cv.qa) + ' / ' + esc(cv.qd) + ' d' : '<span class="fn">No</span>') + '</td><td>' + hc + '</td><td>' + nyCell(r) + '</td></tr>');
  }
  el.innerHTML = '<table class="res"><thead>' + head + '</thead><tbody>' + out.join('') + '</tbody></table>' + (ROWS.length >= MAX ? '<div class="trunc-msg">Showing the first ' + MAX.toLocaleString() + ' rows. Add a plan, state or plan-type filter to narrow the list.</div>' : '');
}
function sortBy(col) {
  if (sortCol === col) sortAsc = !sortAsc; else { sortCol = col; sortAsc = true; }
  const key = r => {
    const p = r.p || {}, cv = r.cv;
    switch (col) {
      case 0: return (r.d.b || r.d.d || '').toLowerCase();
      case 1: return (r.d.s || '').toLowerCase();
      case 2: return (p.pn || '').toLowerCase();
      case 3: return (p.pt || p.mt || '').toLowerCase();
      case 4: return p.st || '';
      case 5: return cv ? parseInt(cv.tier) || 99 : 99;
      case 6: return cv ? getCost(p, cv, r.rx).sort : 999999;
      case 7: return cv ? cv.pa : 'Z';
      case 8: return cv ? cv.st : 'Z';
      case 9: return cv ? cv.ql : 'Z';
      case 10: return r.d.h || '~';
      default: { const m = G.NYMC[r.rx] || ''; return m === 'Y' ? 0 : m === 'X' ? 1 : m === 'N' ? 2 : 3; }
    }
  };
  ROWS.sort((a, b) => { const x = key(a), y = key(b), c = typeof x === 'number' ? x - y : String(x).localeCompare(String(y)); return sortAsc ? c : -c; });
  renderTable();
}
function renderSources() {
  $('sources').innerHTML = '<table class="src"><thead><tr><th scope="col">What it answers</th><th scope="col">Source</th><th scope="col">As of</th></tr></thead><tbody>' +
    G.META.sources.map(s => '<tr><td>' + esc(s[0]) + '</td><td>' + esc(s[1]) + '</td><td>' + esc(s[2]) + '</td></tr>').join('') + '</tbody></table>';
  $('built').textContent = 'Built ' + G.META.built + '.';
}

// ---------- events ----------
document.addEventListener('click', e => {
  const t = e.target.closest('[data-act],[data-year]');
  if (!e.target.closest('#dc')) $('dd').classList.remove('show');
  if (!e.target.closest('#pc')) $('pd').classList.remove('show');
  if (!t) return;
  if (t.dataset.year) { setYear(t.dataset.year); return; }
  const a = t.dataset.act, k = t.dataset.key;
  if (a === 'drug' || a === 'med' || a === 'bs') addDrug(a, k);
  else if (a === 'plan' || a === 'planq') addPlan(a, k);
  else if (a === 'rem') { ({ d: selDrugs, p: selPlans, s: selStates, m: selMT })[t.dataset.kind].splice(+t.dataset.i, 1); renderTags(); }
  else if (a === 'sort') sortBy(+t.dataset.i);
  else if (a === 'search') search();
  else if (a === 'clear') clearAll();
});
document.addEventListener('change', e => {
  const id = e.target.id, v = e.target.value;
  if (id === 'sf' || id === 'mf') { const arr = id === 'sf' ? selStates : selMT; if (v && !arr.includes(v)) arr.push(v); e.target.value = ''; renderTags(); }
  else if (id === 'covSelect') showCov(v);
});
$('di').addEventListener('input', drugKey); $('di').addEventListener('focus', drugKey);
$('pi').addEventListener('input', planKey); $('pi').addEventListener('focus', planKey);
document.addEventListener('keydown', e => { if (e.key === 'Escape') { $('dd').classList.remove('show'); $('pd').classList.remove('show'); } });
document.addEventListener('keydown', e => { if (e.key === 'Enter' && (e.target.id === 'di' || e.target.id === 'pi')) { e.preventDefault(); search(); } });
boot();
