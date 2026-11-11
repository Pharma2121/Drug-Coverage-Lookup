'use strict';
const $ = id => document.getElementById(id);
const MAX = 2000;
let G, D, RX, RXI = {}, DL, CL, Y, YEAR;
const YD = {};
let selDrugs = [], selPlans = [], selStates = ['NY'], selMT = [];
let sortCol = -1, sortAsc = true, ROWS = [], COVB = {}, exampleShown = false;
const MT_TYPES = ['HMO', 'PPO', 'PDP', 'D-SNP', 'C-SNP', 'I-SNP'];

function esc(s) { return s == null ? '' : String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function status(msg) { const el = $('status'); el.textContent = msg || ''; el.hidden = !msg; }

// ---------- data: gzip + base64 blobs embedded in the page ----------
async function unpack(id) {
  const s = atob($(id).textContent.trim());
  const u = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i);
  const st = new Blob([u]).stream().pipeThrough(new DecompressionStream('gzip'));
  return JSON.parse(await new Response(st).text());
}
function extractPT(pn) { const m = pn.match(/\(([^)]+)\)\s*$/); return m ? m[1].trim() : ''; }
function medCat(pt) {
  if (/D-SNP/i.test(pt)) return 'D-SNP';
  if (/C-SNP/i.test(pt)) return 'C-SNP';
  if (/I-SNP/i.test(pt)) return 'I-SNP';
  if (/PDP|Cost/i.test(pt)) return 'PDP';
  if (/PPO|PFFS/i.test(pt)) return 'PPO';
  if (/HMO/i.test(pt)) return 'HMO';
  return 'Other';
}
async function setYear(y) {
  if (!YD[y]) {
    status('Loading ' + y + ' plan data…');
    await new Promise(r => setTimeout(r, 30));
    const d = await unpack('z-' + y);
    d.P.forEach(p => { p.pt = extractPT(p.pn); p.mt = medCat(p.pt); p.sa = p.st ? p.st.split(',') : []; });
    d.FD = {};
    for (const fid in d.C) {
      const a = d.C[fid], m = new Int16Array(RX.length).fill(-1);
      for (let i = 0; i < a.length; i += 2) m[a[i]] = a[i + 1];
      d.FD[fid] = m;
    }
    delete d.C;
    d.F2P = {};
    d.P.forEach(p => { (d.F2P[p.fid] = d.F2P[p.fid] || []).push(p); });
    YD[y] = d;
    status('');
  }
  Y = YD[y]; YEAR = y;
  document.querySelectorAll('[data-year]').forEach(b => b.setAttribute('aria-pressed', b.dataset.year === y ? 'true' : 'false'));
  const m = G.META.years[y];
  $('subtitle').textContent = 'Plan year ' + y + ' · ' + Y.P.length.toLocaleString() + ' Part D plans · ' + RX.length.toLocaleString() + ' drugs · ' + m.label;
  if (selDrugs.length || selPlans.length) search(true);
}
async function boot() {
  if (!('DecompressionStream' in window)) { status('This browser is too old to open the embedded data. Use a current version of Chrome, Edge, Safari or Firefox.'); return; }
  try {
    status('Loading drug and coverage data…');
    G = await unpack('z-common');
    D = G.D; RX = G.RX; CL = G.CL;
    RX.forEach((r, i) => { RXI[r] = i; });
    DL = RX.map(r => { const d = D[r]; d.r = r; const pb = d.h && G.PAYB[d.h]; if (pb) { d.p = pb.p; d.c = pb.c; } return d; });
    const sf = $('sf'); G.STATES.forEach(s => { const o = document.createElement('option'); o.value = s; o.textContent = s; sf.appendChild(o); });
    const mf = $('mf'); MT_TYPES.forEach(t => { const o = document.createElement('option'); o.value = t; o.textContent = t; mf.appendChild(o); });
    renderSources();
    const now = new Date();
    await setYear(now.getFullYear() >= 2027 && YD_HAS('2027') ? '2027' : (YD_HAS(String(now.getFullYear())) ? String(now.getFullYear()) : G.META.default_year));
    renderTags();
    runExample();
  } catch (e) { status('Could not load the embedded data: ' + e.message); }
}
function YD_HAS(y) { return !!G.META.years[y]; }
