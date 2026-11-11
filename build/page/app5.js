
// ---------- coverage summary ----------
function badge(cls, text, tip, href) {
  const t = tip ? ' title="' + esc(tip) + '"' : '';
  return href ? '<a class="cov-badge ' + cls + '" target="_blank" rel="noopener" href="' + esc(href) + '"' + t + '>' + text + '</a>' : '<span class="cov-badge ' + cls + '"' + t + '>' + text + '</span>';
}
function flagTxt(f) {
  const a = [];
  if (f.includes('P')) a.push('PA'); else if (f.includes('p')) a.push('PA if step not met');
  if (f.includes('S')) a.push('ST'); if (f.includes('Q')) a.push('QL'); if (f.includes('M')) a.push('specialty'); if (f.includes('O')) a.push('OTC');
  return a.length ? ' · ' + a.join(' · ') : '';
}
function mcdUrl(kw) {
  return 'https://www.cms.gov/medicare-coverage-database/search.aspx?keyword=' + encodeURIComponent(kw) + '&keywordType=starts&areaId=all&docType=NCA,CAL,NCD,MEDCAC,TA,MCD,6,3,5,1,F,P&contractOption=all&sortBy=relevance&bc=1';
}
function padLookup(code, bn, ds) {
  if (code && G.NYSMED[code]) return { code, rec: G.NYSMED[code] };
  const cand = [(bn || '').toUpperCase().trim()];
  ds.forEach(d => [d.b, d.d].forEach(v => { if (!v) return; v = v.toUpperCase().trim(); cand.push(v, v.replace(/\s+\d.*$/, '').trim()); }));
  for (const c of cand) { const cd = G.PADN[c]; if (cd && G.NYSMED[cd]) return { code: cd, rec: G.NYSMED[cd] }; }
  return null;
}
function partDCov(idx, plans) {                      // across a set of plans: how many list the product, best tier, any UM
  const r = { n: 0, total: plans.length, tier: null, pa: 0, st: 0, ql: 0 };
  for (const p of plans) {
    const m = Y.FD[p.fid]; if (!m) continue;
    let hit = false;
    for (const i of idx) { const cv = pc(m[i]); if (!cv) continue; hit = true; const t = parseInt(cv.tier); if (r.tier == null || t < r.tier) r.tier = t; if (cv.pa === 'Y') r.pa = 1; if (cv.st === 'Y') r.st = 1; if (cv.ql === 'Y') r.ql = 1; }
    if (hit) r.n++;
  }
  return r;
}
function formCov(key, rxs, ds, bn) {                 // plan PDF formularies, matched to RxCUIs at build time
  const F = G.FORM[key]; if (!F) return null;
  let best = null;
  const take = v => {                                // an exact form-and-strength match beats a closest listing; then the lowest tier
    if (!v) return; const [t, f0] = v.split('|'), f = f0 || '', ap = f.includes('~') ? 1 : 0;
    if (!best || ap < best.ap || (ap === best.ap && parseInt(t) < parseInt(best.t))) best = { t, f, ap };
  };
  rxs.forEach(r => take(F.rx[r]));
  if (!best) [bn].concat(ds.map(d => d.b)).forEach(n => { if (n) take(F.bn[n.toUpperCase().trim()]); });
  return { F, best };
}
function planBadges(name, prefix, formKey, med, idx, rxs, ds, bn, code, isMed) {
  let h = '';
  const plans = Y.P.filter(p => (p.cn || '').indexOf(prefix) === 0);
  if (!isMed && plans.length) {
    const c = partDCov(idx, plans);
    h += c.n ? badge('cov-yes', name + ' Medicare: Tier ' + c.tier + (c.pa ? ' · PA' : '') + (c.st ? ' · ST' : '') + (c.ql ? ' · QL' : ''), 'CMS ' + YEAR + ' Part D formulary. Listed by ' + c.n + ' of ' + c.total + ' ' + name + ' Medicare plans; lowest tier shown.')
               : badge('cov-no', name + ' Medicare: not on formulary', 'CMS ' + YEAR + ' Part D formulary, ' + c.total + ' ' + name + ' Medicare plans.');
  }
  const fc = formCov(formKey, rxs, ds, bn);
  if (fc) {
    const tip = fc.F.label + ' (' + fc.F.eff + '). Matched by name from the plan\'s published list; confirm strength and form in the plan document.';
    if (fc.best) h += badge(fc.best.f.includes('P') ? 'cov-warn' : 'cov-yes', name + ' ' + fc.F.short + ': Tier ' + fc.best.t + flagTxt(fc.best.f) + (fc.best.ap ? ' · closest listing' : ''), tip + (fc.best.ap ? ' The list has this drug, but not in exactly this form, release type or strength.' : ''));
    else if (!isMed) h += badge('cov-no', name + ' ' + fc.F.short + ': not listed', tip);
  }
  if (code) {
    const m = med[code];
    if (name === 'Healthfirst') {
      const tip = 'Healthfirst medical-benefit prior authorization grid, revised ' + G.META.hf_grid_rev + '.';
      if (m && m.s === 'P') h += badge('cov-yes', 'Healthfirst medical: Preferred' + (m.a ? ' · PA' : ''), tip);
      else if (m && m.s === 'N') h += badge('cov-warn', 'Healthfirst medical: Non-Preferred' + (m.a ? ' · PA' : ''), tip);
      else if (m && m.s === 'X') h += badge('cov-warn', 'Healthfirst medical: preferred status depends on product' + (m.a ? ' · PA' : ''), tip + ' Brands sharing ' + code + ' have different status.');
      else if (m && m.a) h += badge('cov-warn', 'Healthfirst medical: PA required', tip);
      else h += badge('cov-na', 'Healthfirst medical: not on PA grid', tip + ' ' + code + ' is not listed as requiring prior authorization.');
    } else {
      const tip = 'MetroPlus physician-administered drug authorization grids, updated ' + G.META.mp_grid_upd + '.';
      if (m) {
        const lob = [m.mcr && 'Medicare', m.mcd && 'Medicaid/HARP', m.qhp && 'QHP/EP/CHP'].filter(Boolean).join(', ');
        const pre = m.s === 'P' ? 'Preferred · ' : m.s === 'N' ? 'Non-Preferred · ' : m.s === 'X' ? 'status varies · ' : '';
        h += badge(m.s === 'P' ? 'cov-yes' : 'cov-warn', 'MetroPlus medical: ' + pre + 'PA required (' + lob + ')', tip);
      } else h += badge('cov-na', 'MetroPlus medical: not on PA grid', tip + ' ' + code + ' is not listed as requiring prior authorization.');
    }
  }
  return h;
}
