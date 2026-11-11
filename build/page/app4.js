
// ---------- search ----------
function pc(ci) {
  if (ci == null || ci < 0 || !CL[ci]) return null;
  const s = CL[ci].split('|');
  return { tier: s[0] || '?', pa: s[1] || 'N', st: s[2] || 'N', ql: s[3] || 'N', qa: (s[4] || '').trim(), qd: (s[5] || '').trim(), sel: s[6] || 'N' };
}
const TIER_NAMES = { 1: 'Preferred Generic', 2: 'Generic', 3: 'Preferred Brand', 4: 'Non-Preferred', 5: 'Specialty', 6: 'Select Care' };
const tl = t => TIER_NAMES[t] ? 'Often labelled “' + TIER_NAMES[t] + '”. Plans name their own tiers.' : '';
const yn = v => v === 'Y' ? '<span class="fy">Yes</span>' : '<span class="fn">No</span>';
function getCost(p, cv, rx) {
  const v = Y.COST[p.cid + '|' + p.pid + '|' + cv.tier];
  if (!v) return { html: '<span class="mut">—</span>', sort: 99999 };
  const [ct, ca] = v.split('|'), amt = parseFloat(ca) || 0;
  if (ct === '1') return { html: '<span class="cost-val">$' + amt.toFixed(0) + '</span> <span class="cost-type">copay</span>', sort: amt };
  const up = G.DP[rx];
  if (up) {
    let qty = 30;
    if (cv.ql === 'Y' && cv.qa && cv.qd) qty = (parseFloat(cv.qa) || 0) / (parseFloat(cv.qd) || 1) * 30;
    const est = Math.round(up * qty * amt);
    return { html: '<span class="cost-val">' + (amt * 100).toFixed(0) + '%</span> <span class="cost-type" title="Estimate: ' + (amt * 100).toFixed(0) + '% of the median plan-reported price (' + esc(G.META.price_label) + ') for ' + qty.toFixed(0) + ' units">≈ $' + est.toLocaleString() + '</span>', sort: 1000 + est };
  }
  return { html: '<span class="cost-val">' + (amt * 100).toFixed(0) + '%</span> <span class="cost-type">coinsurance</span>', sort: 1000 + amt * 100 };
}
function planFilter(p) {
  if (selStates.length && !selStates.some(s => p.sa.includes(s))) return false;
  return !selMT.length || selMT.includes(p.mt);
}
function search(keep) {
  const dq = $('di').value.trim(), pq = $('pi').value.trim();
  if (keep !== true) { if (exampleShown && dq.length >= 2) selDrugs = []; exampleShown = false; }
  if (dq.length >= 2) {                                  // typed text adds its best matches to whatever is already selected
    const taken = {}; selDrugs.forEach(s => { taken[s.key] = 1; });
    rankDrugs(dq, 10).forEach(g => { if (taken[g.key]) return; selDrugs.push({ key: g.key, rxcuis: g.items.map(d => d.r) }); taken[g.key] = 1; });
    rankPBD(dq, 10).forEach(x => { const nm = x.e.n || x.code; if (taken[nm] || selDrugs.length >= 20) return; selDrugs.push({ key: nm, rxcuis: [medRx(x.code)], mb: 1 }); taken[nm] = 1; });
    biosimHits(dq, taken).forEach(b => { const nm = b.b || b.g || b.code; if (taken[nm] || selDrugs.length >= 20) return; selDrugs.push({ key: nm, rxcuis: [bsRx(b.code)], bs: 1 }); taken[nm] = 1; });
  }
  if (pq.length >= 2 && !selPlans.find(s => s.key === pq) && Y.P.some(p => fuzzyMatch(pq, p.pn || '', p.cn || '', p.cid || ''))) selPlans.push({ key: pq, q: true });
  renderTags();
  $('di').value = ''; $('pi').value = '';
  $('dd').classList.remove('show'); $('pd').classList.remove('show');
  if (!selDrugs.length && !selPlans.length) return;

  let pool = [];
  if (selPlans.length) { const seen = new Set(); selPlans.forEach(s => planMatches(s).forEach(p => { if (planFilter(p) && !seen.has(p)) { seen.add(p); pool.push(p); } })); }
  else pool = Y.P.filter(planFilter);

  const rows = [], allRx = [];
  selDrugs.forEach(s => s.rxcuis.forEach(r => { if (!allRx.includes(r)) allRx.push(r); }));
  if (selDrugs.length) {
    outer: for (const rx of allRx) {
      const d = D[rx];
      if (d.bs || d.mb) { rows.push({ rx, d, p: null, cv: null }); continue; }
      const i = RXI[rx];
      for (const p of pool) {
        const m = Y.FD[p.fid]; if (!m) continue;
        rows.push({ rx, d, p, cv: pc(m[i]) });
        if (rows.length >= MAX) break outer;
      }
    }
  } else {
    outer2: for (const p of pool) {
      const m = Y.FD[p.fid]; if (!m) continue;
      for (let i = 0; i < m.length; i++) if (m[i] >= 0) { rows.push({ rx: RX[i], d: D[RX[i]], p, cv: pc(m[i]) }); if (rows.length >= MAX) break outer2; }
    }
  }
  const cov = rows.filter(r => r.cv).length, not = rows.filter(r => r.p && !r.cv).length;
  $('summary').innerHTML = (exampleShown ? '<span class="example">Example search</span> ' : '') + 'Plan year <strong>' + YEAR + '</strong> · ' + pool.length.toLocaleString() + ' plans in view · <strong>' + cov.toLocaleString() + '</strong> on formulary' +
    (not ? ' · <strong>' + not.toLocaleString() + '</strong> not on formulary' : '') + (rows.length >= MAX ? ' · <em>first ' + MAX.toLocaleString() + ' rows shown</em>' : '');

  if (selDrugs.length) {
    COVB = {};
    allRx.forEach(rx => { const k = dkey(D[rx]); (COVB[k] = COVB[k] || []).push(rx); });
    const keys = Object.keys(COVB);                       // best match first
    $('covpanel').innerHTML = '<div class="cov-panel"><div class="cov-head"><h2>Coverage summary</h2><label class="sr" for="covSelect">Product</label><select id="covSelect">' +
      keys.map(k => '<option value="' + esc(k) + '">' + esc(k) + '</option>').join('') + '</select><span class="cov-pool" id="covPool"></span></div><div id="covBadges"></div></div>';
    window._pool = pool;
    showCov(keys[0]);
  } else $('covpanel').innerHTML = '';
  ROWS = rows; sortCol = -1; renderTable();
}
