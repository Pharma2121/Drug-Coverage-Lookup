
// ---------- drug and plan matching ----------
// Ranking: exact > starts-with > all-tokens > substring; brand outranks description. HCPCS codes are searchable.
// Typo tolerance runs only when nothing matched, and those results are flagged "did you mean".
function norm(s) { return s ? s.replace(/[^a-zA-Z0-9]/g, '').toLowerCase() : ''; }
function fuzzyMatch(q, ...t) { const qn = norm(q); return !!qn && t.some(x => norm(x).includes(qn)); }
function nrm(s) { return (s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').replace(/(\d)\s+(mg|ml|mcg|g|unt|unit|units|iu|meq|pct)\b/g, '$1$2').trim(); }
function toks(s) { const t = nrm(s); if (!t) return []; const a = t.split(' '), b = a.filter(x => x.length > 1); return b.length ? b : a; }
function lev(a, b) {
  if (Math.abs(a.length - b.length) > 2) return 9;
  let prev = [], cur = [];
  for (let j = 0; j <= b.length; j++) prev[j] = j;
  for (let i = 1; i <= a.length; i++) {
    cur[0] = i;
    for (let j = 1; j <= b.length; j++) cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    prev = cur.slice();
  }
  return prev[b.length];
}
function scoreText(q, qt, txt, base) {
  if (!txt) return 0;
  const t = nrm(txt); if (!t) return 0;
  if (t === q) return base + 400;
  if (t.indexOf(q) === 0) return base + 300;
  if ((' ' + t).indexOf(' ' + q) >= 0) return base + 200;
  if (qt.length > 1 && qt.every(x => t.indexOf(x) >= 0)) return base + 150;
  if (t.indexOf(q) >= 0) return base + 60;
  return 0;
}
function scoreDrug(d, q, qt) {
  let s = Math.max(scoreText(q, qt, d.b, 600), scoreText(q, qt, d.d, 300), scoreText(q, qt, d.s, 200));
  if (!d.b && d.g) s = Math.max(s, scoreText(q, qt, d.g, 620));        // a generic-name query should surface the generic first
  if (d.h) { const hq = q.replace(/\s+/g, ''), h = nrm(d.h); if (h === hq) return 1200; if (h.indexOf(hq) === 0 && hq.length >= 3) s = Math.max(s, 900); }
  return s;
}
const dkey = d => d.b || (d.g ? d.g + ' (' + (d.f || 'generic').toLowerCase() + ')' : d.d) || d.r;   // brands by name, generics by ingredient and form
function rankDrugs(q, limit) {
  const qn = nrm(q), qt = toks(q); if (!qn) return [];
  const groups = {};
  for (const d of DL) {
    let sc = scoreDrug(d, qn, qt); if (!sc) continue;
    if (d.b) sc += 40;
    const k = dkey(d), g = groups[k] || (groups[k] = { key: k, items: [], score: 0, br: !!d.b });
    g.items.push(d); if (sc > g.score) g.score = sc;
  }
  let out = Object.values(groups);
  if (!out.length && qn.length >= 4) {
    const seen = {};
    for (const d of DL) {
      const bn = nrm(d.b); if (!bn || seen[bn]) continue;
      const dist = lev(qn, bn);
      if (dist <= (qn.length <= 6 ? 1 : 2)) { seen[bn] = 1; const k = dkey(d); out.push({ key: k, items: DL.filter(z => dkey(z) === k), score: 50 - dist, fuzzy: true, br: true }); }
      if (out.length >= 8) break;
    }
  }
  out.sort((a, b) => b.score - a.score || (b.br ? 1 : 0) - (a.br ? 1 : 0) || a.key.length - b.key.length || a.key.localeCompare(b.key));
  return limit ? out.slice(0, limit) : out;
}
function molScore(q, qt, e) { const s = e.m ? scoreText(q, qt, e.m, 540) : 0; return s && !e.bio ? s + 5 : s; }   // a molecule query lists the reference product first, then its biosimilars
function rankPBD(q, limit) {
  const qn = nrm(q), qt = toks(q); if (!qn) return [];
  const out = [];
  for (const code in G.PBD) {
    const e = G.PBD[code]; let s = 0;
    if (nrm(code) === qn.replace(/\s+/g, '')) s = 1200;
    else s = Math.max(scoreText(qn, qt, e.n, 600), scoreText(qn, qt, e.sd, 300), e.alt ? scoreText(qn, qt, e.alt.join(' '), 250) : 0,
      e.g ? scoreText(qn, qt, e.g, 520) : 0, molScore(qn, qt, e));
    if (s) out.push({ code, e, score: s });
  }
  out.sort((a, b) => b.score - a.score || a.e.n.localeCompare(b.e.n));
  return limit ? out.slice(0, limit) : out;
}
function biosimHits(q, taken) {
  const out = [];
  for (const code in G.BIOSIM) { const b = G.BIOSIM[code]; if (!G.PBD[code] && fuzzyMatch(q, b.b || '', b.g || '', code) && !taken[b.b || b.g || code]) out.push({ code, b: b.b, g: b.g }); }
  return out;
}
// ---------- same-ingredient index ----------
// ING[ingredient][group key] = { h: the group's HCPCS code, sufs: suffixed names in the group such as "adalimumab-adaz", plain: products without one }
// MOLC[ingredient] = HCPCS codes for that molecule (reference product and biosimilars), set at build time by biosimilars.py.
let ING = {}, MOLC = {}, MEDN = {}, BRAND = {};
function indexIngredients() {
  for (const d of DL) {
    if (d.b) BRAND[d.b] = 1;
    if (!d.g) continue;
    const grp = ING[d.g] || (ING[d.g] = {}), k = dkey(d), it = grp[k] || (grp[k] = { h: '', sufs: [], plain: 0 });
    if (d.h && !it.h) it.h = d.h;
    const i = (d.d || '').indexOf(d.g + '-'), m = i >= 0 && /^-[A-Z]{4}\b/.exec(d.d.slice(i + d.g.length)), suf = m ? (d.g + m[0]).toLowerCase() : '';
    if (!suf) it.plain++; else if (!it.sufs.includes(suf)) it.sufs.push(suf);
  }
  for (const code in G.PBD) {
    const e = G.PBD[code]; MEDN[e.n] = (MEDN[e.n] || 0) + 1;
    if (e.m) { const g = e.m.toUpperCase(); (MOLC[g] = MOLC[g] || []).push(code); }
  }
}
// The code a selection's coverage summary shows is the first one among its products; a medical-benefit entry for that code would repeat it.
function shownCodes(lists) { const s = new Set(); lists.forEach(items => { const d = items.find(x => x && x.h); if (d) s.add(d.h); }); return s; }
// Two codes can share a brand (Wezlana SC and IV), and a brand can be both a Part D product and a medical code: those get the code in the name.
function medName(code) { const n = G.PBD[code].n || code; return MEDN[n] > 1 || BRAND[n] ? n + ' (' + code + ')' : n; }
function medSub(code, e) {
  if (G.NOTPAYB[code]) return 'Medical benefit · not payable under Part B';
  return (e.bio ? 'Biosimilar' + (e.g ? ' · ' + e.g : '') + ' · medical benefit' : 'Medical benefit · ' + (e.sd || '')) + (e.bio && e.alt && e.alt.length ? ' · also ' + e.alt.join(', ') : '') + (e.end ? ' · code ended ' + e.end : '');
}
function medRx(code) {                         // a medical-benefit-only product gets a synthetic id
  const id = 'PB_' + code, e = G.PBD[code];
  if (!D[id]) { const pb = G.PAYB[code] || {}; D[id] = { r: id, b: medName(code), n0: e.n || '', d: e.ld || e.sd || '', s: e.do || '', f: 'MEDICAL BENEFIT', g: (e.m || '').toUpperCase(), h: code, p: pb.p || '', c: pb.c || '', mb: 1 }; }
  return id;
}
function sameIng(ds) {                         // every product sharing the active ingredient: Part D groups, then medical codes not already shown by one
  const g = (ds.find(d => d.g) || {}).g; if (!g) return null;
  const items = [], shown = new Set(), grp = ING[g] || {};
  for (const key in grp) {
    const it = grp[key], e = it.h ? G.PBD[it.h] : null;
    // a Part D group is labelled biosimilar only when its HCPCS code is one CMS describes as a biosimilar; otherwise it shows its suffixed name
    const bio = !!(e && e.bio && (e.m || '').toUpperCase() === g);
    const sub = it.sufs.slice(0, 4).map((x, i) => i ? x.slice(g.length) : x).join(', ') + (it.sufs.length > 4 ? ', …' : '');
    if (it.h) shown.add(it.h);
    items.push({ kind: 'drug', key, name: key, code: it.h, bio, sub });
  }
  (MOLC[g] || []).forEach(code => { if (shown.has(code)) return; const e = G.PBD[code]; items.push({ kind: 'med', key: code, name: e.n || code, code, bio: !!e.bio, sub: e.g || '' }); });
  if (items.length < 2) return null;
  const late = it => (it.bio || it.sub ? 1 : 0);  // originator and unsuffixed products first
  items.sort((a, b) => late(a) - late(b) || a.name.localeCompare(b.name) || (a.kind === 'drug' ? 0 : 1) - (b.kind === 'drug' ? 0 : 1) || a.key.localeCompare(b.key));
  return { g, items };
}
function bsRx(code) {
  const id = 'BS_' + code, b = G.BIOSIM[code];
  if (!D[id]) D[id] = { r: id, b: b.b || '', d: b.g || '', s: '', f: 'MEDICAL BENEFIT', g: '', h: code, bs: 1 };
  return id;
}
function planMatches(sel) {
  return sel.q ? Y.P.filter(p => fuzzyMatch(sel.key, p.pn || '', p.cn || '', p.cid || '')) : Y.P.filter(p => (p.cn || p.cid) === sel.key);
}
