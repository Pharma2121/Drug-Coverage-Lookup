function ingRow(k, ds) {
  const s = sameIng(ds); if (!s) { window._ing = []; return ''; }
  window._ing = s.items;
  const max = 40, chips = s.items.slice(0, max).map(it => {
    const e = it.kind === 'med' ? G.PBD[it.key] : null, cur = (e ? medName(it.key) : it.key) === k;
    const tip = e ? (e.ld || e.sd || '') + '. Medical benefit' + (e.eff ? '; code effective ' + e.eff : '') + (e.end ? '; code ended ' + e.end : '') + '.'
                  : 'Part D product' + (it.sub ? ': ' + it.sub : '') + (it.code ? '; HCPCS ' + it.code : '') + '.';
    const inner = '<span class="nm">' + esc(it.name) + '</span>' + (e ? ' <span class="cd">' + esc(it.key) + '</span>' : '') +
      (it.bio ? ' <span class="bs">biosimilar</span>' : it.sub ? ' <span class="cd">' + esc(it.sub) + '</span>' : '');
    return cur ? '<span class="ing-chip cur" aria-current="true" title="' + esc(tip) + '">' + inner + '</span>'
               : '<button type="button" class="ing-chip" data-act="ing" data-kind="' + it.kind + '" data-key="' + esc(it.key) + '" title="' + esc(tip + ' Select to add it to the comparison.') + '">' + inner + '</button>';
  }).join('');
  const more = s.items.length > max ? '<span class="mut">+' + (s.items.length - max) + ' more</span>' : '';
  const all = s.items.length > 2 ? '<button type="button" class="ing-all" data-act="ingall">Compare all ' + Math.min(s.items.length, max) + '</button>' : '';
  const tip = 'Products with the same active ingredient in the source files. “Biosimilar” is shown where the CMS HCPCS code descriptor says so. The Part D files do not flag biosimilars, so pharmacy products show their suffixed name instead.';
  return '<div class="cov-row"><span class="cov-lab" title="' + esc(tip) + '">Same ingredient</span><div class="cov-badges"><span class="ing-name">' + esc(s.g.toLowerCase()) + '</span>' + chips + more + all + '</div></div>';
}
// ---------- eligibility at a glance ----------
// Medicare eligible: a Medicare drug plan in view lists the product (Part D), or its HCPCS code has a Part B payment limit.
// NY Medicaid eligible: the product is in the NYRx pharmacy file, or its code is on the PAD list or the physician drug fee schedule.
// "Not confirmed": the code exists but has no Part B payment limit, which CMS says is not a coverage decision.
function elig(k) {
  const rxs = COVB[k] || [], ds = rxs.map(r => D[r]), isMed = ds.some(d => d.mb || d.bs), pool = window._pool || [];
  let code = ''; ds.forEach(d => { if (d.h && !code) code = d.h; });
  const idx = rxs.map(r => RXI[r]).filter(i => i != null);
  const c = isMed ? { n: 0, total: pool.length } : partDCov(idx, pool);
  const nb = code && G.NOTPAYB[code], pb = code && !nb && G.PAYB[code];
  let mcr;
  if (c.n || pb) mcr = { v: 'Yes', cls: 'yes', via: [c.n ? 'Part D' + (c.n < c.total ? ', ' + c.n.toLocaleString() + ' of ' + c.total.toLocaleString() + ' plans' : '') : '', pb ? 'Part B' : ''].filter(Boolean).join(' and '),
    why: [c.n ? c.n.toLocaleString() + ' of ' + c.total.toLocaleString() + ' Medicare drug plans in view list it for ' + YEAR + '.' : '', pb ? code + ' has a Part B payment limit for ' + G.META.partb_eff + '.' : ''].filter(Boolean).join(' ') };
  else if (code && !nb && (isMed || !isNOC(code))) mcr = { v: 'Not confirmed', cls: 'na', via: 'no Part B payment limit',
    why: code + ' has no Part B payment limit for ' + G.META.partb_eff + '. CMS says that is not a coverage decision; the local Medicare contractor decides.' + (isMed ? '' : ' No Medicare drug plan in view lists it.') };
  else mcr = { v: 'No', cls: 'no', via: nb ? 'not payable under Part B' : '',
    why: (nb ? code + ' is on the CMS list of drugs not payable under Part B. ' : '') + (isMed ? '' : 'No Medicare drug plan in view lists it for ' + YEAR + '.') + (!code ? ' No HCPCS code is linked to it.' : !nb ? ' ' + code + ' is an unclassified code with no Part B payment limit.' : '') };
  let ny = null; rxs.forEach(r => { const v = G.NYMC[r]; if (v === 'Y' || (v === 'X' && ny !== 'Y') || (v === 'N' && !ny)) ny = v; });
  const pad = padLookup(code, k, ds), fs = code ? G.NYSFS[code] : null, med = !!(pad || fs);
  const mcd = ny || med
    ? { v: 'Yes', cls: 'yes', via: [ny ? 'pharmacy' : '', med ? 'medical' : ''].filter(Boolean).join(' and ') + ' benefit',
        why: [ny ? 'In the NYRx pharmacy file (' + (ny === 'Y' ? 'preferred' : ny === 'N' ? 'non-preferred' : 'covered') + '), ' + G.META.nyrx_date + '.' : '',
              med ? (pad ? pad.code + ' is on the NYS physician-administered drug list, ' + G.META.pad_eff : code + ' is on the NYS physician drug fee schedule, ' + G.META.nysfs_eff) + '.' : ''].filter(Boolean).join(' ') + ' Fee-for-service; prior authorization may still apply.' }
    : { v: 'No', cls: 'no', via: '', why: 'Not in the NYRx pharmacy file' + (!code ? ', and no HCPCS code is linked to it.' : ', and ' + code + ' is not on the physician-administered drug list or the fee schedule.') + ' A Medicaid managed care plan may still cover it under its own rules.' };
  // values typed in by hand in an earlier build, kept as a cross-check and shown only against the product they name
  let hand = null; [k].concat(ds.map(d => d.b || '')).forEach(n => { const v = G.OVR[(n || '').toLowerCase().trim()]; if (v && !hand) hand = v; });
  return { mcr, mcd, code, hand };
}
const ELIG_TIP = 'Medicare eligible: a Medicare drug plan in view lists it, or its HCPCS code has a Part B payment limit. NY Medicaid eligible: it is in the NYRx pharmacy file, or its code is on the state physician-administered drug list or fee schedule. Eligible is not the same as approved: prior authorization and plan rules still apply.';
function eligRow(k) {
  const e = elig(k), b = (lab, x) => badge('cov-' + x.cls, lab + ': ' + x.v + (x.via ? ' · ' + esc(x.via) : ''), x.why);
  let hand = '';
  if (e.hand) {
    const diff = [];
    if ((e.hand.mcr === 'Y') !== (e.mcr.v === 'Yes')) diff.push('Medicare ' + (e.hand.mcr === 'Y' ? 'covered' : 'not covered'));
    if ((e.hand.mcd === 'Y') !== (e.mcd.v === 'Yes')) diff.push('Medicaid ' + (e.hand.mcd === 'Y' ? 'covered' : 'not covered'));
    hand = diff.length ? badge('cov-warn', 'Entered by hand earlier: ' + diff.join(', '), 'An earlier build carried this value, typed in by hand and undated. The source files read for this build say otherwise. Check before relying on either.')
                       : '<span class="mut">matches the values entered by hand in an earlier build</span>';
  }
  return '<div class="cov-row"><span class="cov-lab" title="' + esc(ELIG_TIP) + '">At a glance</span><div class="cov-badges">' + b('Medicare eligible', e.mcr) + b('NY Medicaid eligible', e.mcd) + hand + '</div></div>';
}
function eligTable(keys, cur) {                 // one line per selected product, so a group can be compared without opening each one
  if (keys.length < 2) return '';
  const cell = x => '<td title="' + esc(x.why) + '"><span class="pill ' + x.cls + '">' + x.v + '</span>' + (x.via ? ' <span class="mut">' + esc(x.via) + '</span>' : '') + '</td>';
  const rows = keys.slice(0, 60).map(k => { const e = elig(k);
    return '<tr' + (k === cur ? ' class="cur"' : '') + '><th scope="row"><button type="button" data-act="covpick" data-key="' + esc(k) + '" title="Show the full coverage summary">' + esc(k) + '</button>' + (e.code && k.indexOf(e.code) < 0 ? ' <span class="code">' + esc(e.code) + '</span>' : '') + '</th>' + cell(e.mcr) + cell(e.mcd) + '</tr>'; }).join('');
  return '<div class="cov-row"><span class="cov-lab" title="' + esc(ELIG_TIP) + '">All selected</span><div class="elig-wrap"><table class="elig"><thead><tr><th scope="col">Product</th><th scope="col">Medicare eligible</th><th scope="col">NY Medicaid eligible</th></tr></thead><tbody>' +
    rows + '</tbody></table>' + (keys.length > 60 ? '<div class="mut">First 60 of ' + keys.length + ' shown.</div>' : '') + '</div></div>';
}
function showCov(k) {
  const rxs = COVB[k] || [], pool = window._pool || [];
  if (!rxs.length) { $('covBadges').innerHTML = ''; return; }
  const ds = rxs.map(r => D[r]), isMed = ds.some(d => d.mb || d.bs);
  let code = ''; ds.forEach(d => { if (d.h && !code) code = d.h; });
  const idx = rxs.map(r => RXI[r]).filter(i => i != null), M = G.META;
  let h = eligRow(k) + '<div class="cov-row"><span class="cov-lab">Public programs</span><div class="cov-badges">';

  // Medicare Part D, across the plans currently in view
  if (isMed) h += badge('cov-na', 'Medicare Part D: medical-benefit product', 'Billed under the medical benefit; not on Part D pharmacy formularies.');
  else {
    const c = partDCov(idx, pool);
    $('covPool').textContent = c.total.toLocaleString() + ' plans in view';
    h += c.n ? badge(c.n === c.total ? 'cov-yes' : 'cov-part', 'Medicare Part D: ' + c.n.toLocaleString() + ' of ' + c.total.toLocaleString() + ' plans', 'Plans in view (' + YEAR + ') that list any strength of this product. Lowest tier ' + c.tier + '.')
               : badge('cov-no', 'Medicare Part D: no plan in view lists it', c.total + ' plans checked for plan year ' + YEAR + '.');
  }
  // Medicare Part B. Per CMS, absence from the Payment Limit File is not a coverage determination.
  const nb = code && G.NOTPAYB[code], pb = code && G.PAYB[code];
  if (nb) h += badge('cov-no', 'Medicare Part B: not payable (' + esc(code) + ')', nb.ld + '. Manufacturer ' + nb.m + ' has no Medicaid rebate agreement in effect (' + M.partb_eff + ').');
  else if (pb) h += badge('cov-yes', 'Medicare Part B: ' + esc(code) + ' · $' + esc(pb.p) + (pb.do ? ' per ' + esc(pb.do) : ''), (pb.sd || '') + '. Payment limit ' + M.partb_eff + (pb.c ? '; coinsurance ' + parseFloat(pb.c) + '%' : '') + '. The MAC makes the coverage decision.');
  else if (code) { const pe = G.PBD[code] || {};
    h += pe.end ? badge('cov-warn', 'Medicare Part B: ' + esc(code) + ' ended ' + esc(pe.end), 'CMS ended this HCPCS code on ' + pe.end + '. A plan list may still name it.')
                : badge('cov-na', 'Medicare Part B: ' + esc(code) + ' not on payment file', 'Not on the Payment Limit File for ' + M.partb_eff + '.' + (pe.eff ? ' CMS made the code effective ' + pe.eff + '.' : '') + ' Per CMS this is not a coverage determination; the local MAC may still pay the claim.'); }
  else h += badge('cov-na', 'Medicare Part B: no HCPCS code', 'No HCPCS code is linked to this product in the CMS crosswalks or the NY PAD list.');

  // NY Medicaid pharmacy benefit (NYRx)
  const nyTip = 'eMedNY reimbursable drug file, ' + M.nyrx_date + '. NYRx governs mainstream managed care, HARP and HIV-SNP since 4/1/2023. It does not apply to Essential Plan, Child Health Plus or MLTC/MAP/PACE.';
  let ny = null, nypa = null;
  rxs.forEach(r => { const v = G.NYMC[r]; if (v === 'Y' || (v === 'X' && ny !== 'Y') || (v === 'N' && !ny)) ny = v; if (G.NYPA[r] === 'N') nypa = 'N'; else if (G.NYPA[r] === 'G' && !nypa) nypa = 'G'; });
  const paTxt = nypa === 'N' ? ' · PA' : '', paTip = nypa === 'G' ? ' PA applies if non-preferred or clinical criteria are not met.' : nypa === 'N' ? ' Prior authorization required.' : '';
  if (ny === 'Y') h += badge('cov-yes', 'NY Medicaid: Preferred' + paTxt, nyTip + paTip);
  else if (ny === 'N') h += badge('cov-warn', 'NY Medicaid: Non-Preferred' + paTxt, nyTip + paTip);
  else if (ny === 'X') h += badge('cov-yes', 'NY Medicaid: Covered' + paTxt, nyTip + ' Not a Preferred Drug List class.' + paTip);
  else if (isMed) h += badge('cov-na', 'NY Medicaid pharmacy: medical-benefit product', 'Not in the NYRx retail pharmacy file. See the medical badge.');
  else h += badge('cov-no', 'NY Medicaid: not in NYRx file', nyTip + ' This product\'s NDC was not found; another labeler\'s version may be reimbursable.');

  // NY Medicaid medical benefit: PAD list first, then the Physician Drug Fee Schedule
  const pad = padLookup(code, k, ds), fs = code ? G.NYSFS[code] : null;
  if (pad || fs) {
    const pr = pad ? pad.rec : null, pcode = pad ? pad.code : code;
    const srcTxt = (pad ? 'NYS List of Physician Administered Drugs, ' + M.pad_eff : 'NYS Physician Drug Fee Schedule, effective ' + M.nysfs_eff) + (fs && fs.br ? '; priced By Report' : '') + '. ' + (pr ? pr.n : fs.d);
    const pa = (pr && pr.pa) || (fs && fs.pa), mr = pr && pr.mr;
    h += badge(pa || mr ? 'cov-warn' : 'cov-yes', 'NY Medicaid medical: ' + esc(pcode) + (pa ? ' · PA required' : mr ? ' · manual review' : ' · covered'), srcTxt);
  } else if (code) h += badge('cov-no', 'NY Medicaid medical: ' + esc(code) + ' not listed', 'Not on the PAD list (' + M.pad_eff + ') or the Physician Drug Fee Schedule (' + M.nysfs_eff + ').');
  const key = code || ds[0].b || ds[0].g || k;
  h += badge('cov-link', 'Coverage DB: ' + esc(key) + ' ↗', 'Open the CMS Medicare Coverage Database (LCDs and billing articles) for ' + key, mcdUrl(key));
  h += '</div></div>';

  h += '<div class="cov-row"><span class="cov-lab">Healthfirst</span><div class="cov-badges">' + planBadges('Healthfirst', 'HEALTHFIRST', 'hf' + YEAR.slice(2), G.HFPA, idx, rxs, ds, k, code, isMed) + '</div></div>';
  h += '<div class="cov-row"><span class="cov-lab">MetroPlus</span><div class="cov-badges">' + planBadges('MetroPlus', 'METROPLUS', 'mp', G.MPPA, idx, rxs, ds, k, code, isMed) + '</div></div>';
  h += ingRow(k, ds);

  $('covBadges').innerHTML = h;
  if ($('covAll')) $('covAll').innerHTML = eligTable(Object.keys(COVB), k);
}
