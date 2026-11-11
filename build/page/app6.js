function showCov(k) {
  const rxs = COVB[k] || [], pool = window._pool || [];
  if (!rxs.length) { $('covBadges').innerHTML = ''; return; }
  const ds = rxs.map(r => D[r]), isMed = ds.some(d => d.mb || d.bs);
  let code = ''; ds.forEach(d => { if (d.h && !code) code = d.h; });
  const idx = rxs.map(r => RXI[r]).filter(i => i != null), M = G.META;
  let h = '<div class="cov-row"><span class="cov-lab">Public programs</span><div class="cov-badges">';

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
  else if (code) h += badge('cov-na', 'Medicare Part B: ' + esc(code) + ' not on payment file', 'Not on the Payment Limit File for ' + M.partb_eff + '. Per CMS this is not a coverage determination; the local MAC may still pay the claim.');
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

  // manually verified coverage carried from earlier builds
  const blob = (k + ' ' + ds.map(d => (d.b || '') + ' ' + (d.d || '')).join(' ')).toLowerCase();
  for (const o in G.OVR) if (blob.indexOf(o) >= 0) {
    const v = G.OVR[o];
    h = '<div class="cov-row ovr"><span class="cov-lab">Verified by hand</span><div class="cov-badges">' + badge(v.mcr === 'Y' ? 'cov-yes' : 'cov-no', 'Medicare: ' + (v.mcr === 'Y' ? 'Covered' : 'Not covered')) +
      badge(v.mcd === 'Y' ? 'cov-yes' : 'cov-no', 'Medicaid: ' + (v.mcd === 'Y' ? 'Covered' : 'Not covered')) + '<span class="mut">entered manually in an earlier build; the rows below are from the source files</span></div></div>' + h;
    break;
  }
  $('covBadges').innerHTML = h;
}
