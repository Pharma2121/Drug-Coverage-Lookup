"""Reconcile the finished index.html against the raw source files. Run after stage 5.
Every figure the page can show for Part D and Part B is re-read from the page's own embedded data and compared with the source rows."""
import base64, gzip, random, collections, sys
from common import *
from stage2_drugs import read_csv_table, find
from biosimilars import load_hcpcs, parse_descriptor, ny_generic, base, nrm, NOT_SAME

FAILS = []
def check(name, ok, detail=''):
    print(('PASS  ' if ok else 'FAIL  ') + name + (('  | ' + detail) if detail else ''))
    if not ok: FAILS.append(name)

def blobs(path):
    html = open(path, encoding='utf-8').read()
    out_ = {}
    for m in re.finditer(r'<script type="application/octet-stream" id="z-(\w+)">([^<]+)</script>', html):
        out_[m.group(1)] = json.loads(gzip.decompress(base64.b64decode(m.group(2))))
    return out_

def grid_rows():
    """Text around every Q5 code printed in the plans' authorization grids: {code: [text, ...]}. None when the PDFs are not in sources/."""
    import glob
    files = sorted(glob.glob(src('Prior-Authorization-Medical-Benefit-Grid*.pdf'))) + sorted(glob.glob(src('PAD-Auth-Grid*.pdf')))
    if not files: return None
    import pymupdf
    out = {}
    for f in files:
        for page in pymupdf.open(f):
            words = page.get_text('words')
            for w in words:
                m = re.match(r'(Q5\d{3})', w[4])
                if not m: continue
                y = (w[1] + w[3]) / 2
                out.setdefault(m.group(1), []).append(' '.join(x[4] for x in words if abs((x[1] + x[3]) / 2 - y) < 26).lower())
    return out

def check_biosimilars(G):
    """Needs only the page and sources/hcpcs_biosimilar_codes.csv, so it can run without the large source files:
    python3 verify_build.py --biosimilars"""
    HC, PBD, D = load_hcpcs(), G['PBD'], G['D']
    desc = lambda c: ' | '.join(x for x in ((G['PAYB'].get(c) or {}).get('sd'), (G['NYSMED'].get(c) or {}).get('n'), (G['NYSFS'].get(c) or {}).get('d'), PBD[c].get('sd')) if x).lower()
    names = lambda e: [nrm(e['n'])] + [nrm(a) for a in e.get('alt', [])]
    active = {c: h for c, h in HC.items() if not h['term']}
    bad = []
    for c, h in active.items():
        g, brands, dose, route = parse_descriptor(h['ld']); e = PBD.get(c)
        if not e or not e.get('bio') or e.get('g') != g or e.get('m') != base(g) or (e.get('ld') or e['sd']) != h['ld'] or any(not any(nrm(b) in k for k in names(e)) for b in brands): bad.append(c)
    check('biosimilars: every active CMS biosimilar code is in the page with its name, molecule and brands', not bad, f'{len(active)} active codes' + (f'; wrong: {bad}' if bad else ''))
    ended = [c for c, h in HC.items() if h['term'] and c in PBD and not PBD[c].get('end')]
    check('biosimilars: an ended code is either left out or marked ended', not ended, f"{sum(1 for c, h in HC.items() if h['term'] and c in PBD)} ended codes kept, {sum(1 for c, h in HC.items() if h['term'] and c not in PBD)} left out")
    bio = {c: e for c, e in PBD.items() if e.get('bio')}
    odd = [c for c, e in bio.items() if not e.get('m') or not e.get('g') or (c not in HC and (not c.startswith('Q') or e['g'] not in desc(c)))]
    check('biosimilars: every flagged code has a name and molecule traceable to a descriptor', not odd, f"{len(bio)} flagged; {sum(1 for c in bio if c not in HC)} outside the Q5 range, by the suffixed name in their own description" + (f'; {odd}' if odd else ''))
    groups = collections.defaultdict(lambda: [[], []])
    for c, e in PBD.items():
        if e.get('m'): groups[e['m']][1 if e.get('bio') else 0].append(c)
    noref = [m for m, (ref, bs) in groups.items() if bs and not ref]
    check('biosimilars: every molecule with a biosimilar also has its reference product', not noref, f'{len(groups)} molecules' + (f'; none for {noref}' if noref else ''))
    wrong = [c for m, (ref, bs) in groups.items() for c in ref if any(t in desc(c) for t in NOT_SAME) or not re.search(r'(?<![a-z\-])' + re.escape(m) + r'(?![a-z])', desc(c))]
    check('biosimilars: no conjugate, combination or differently named product sits in a molecule group', not wrong, f"{sum(len(ref) for ref, bs in groups.values())} non-biosimilar codes in groups" + (f'; {wrong}' if wrong else ''))
    ny = [(c, ny_generic(d_)) for c in bio if c in HC for d_ in ((G['NYSMED'].get(c) or {}).get('n'), (G['NYSFS'].get(c) or {}).get('d')) if ny_generic(d_)]   # an independent source: the NY lists
    check('biosimilars: the CMS name agrees with the NY Medicaid description wherever NY writes one', all(g == PBD[c]['g'] for c, g in ny), f'{len({c for c, g in ny})} codes compared')
    linked = [(rx, d) for rx, d in D.items() if d.get('hn')]
    badl = [rx for rx, d in linked if d['h'] not in active or d['g'].lower() != PBD[d['h']]['m'] or nrm(d['b']) not in [nrm(b) for b in parse_descriptor(active[d['h']]['ld'])[1]]]
    check('biosimilars: a Part D product linked by brand name matches the code\'s molecule and a brand in its descriptor', not badl, f'{len(linked)} products: {sorted({(d["b"], d["h"]) for rx, d in linked})}')
    # the page's "at a glance" answer for a medical-benefit code, re-derived here from the same tables
    noc = lambda c: bool(re.search(r'UNCLASSIFIED|NOT OTHERWISE CLASSIFIED', ((G['NYSMED'].get(c) or {}).get('n', '') + ' ' + (G['NYSFS'].get(c) or {}).get('d', '') + ' ' + PBD[c].get('sd', '')).upper()))
    mcr = lambda c: 'No' if c in G['NOTPAYB'] else 'Yes' if c in G['PAYB'] else 'Not confirmed'
    mcd = lambda c: 'Yes' if c in G['NYSMED'] or c in G['NYSFS'] else 'No'
    # Part D products that carry a catch-all code (J3490, J3590, J9999): the page reads the code's place on the NY list as the product's,
    # which holds only if the list names each of those products under that code. Names differ in small ways: "HYRIMOZ(CF)", "EGRIFTA SV",
    # "POLYMYXIN B SULFATE", a kit named after its brand.
    under = collections.defaultdict(set)
    for n, cd in G['PADN'].items(): under[cd].add(n)
    for cd, r in G['NYSMED'].items(): under[cd] |= {n.upper() for n in r.get('d', [])}
    def named_under(rxs, code):
        cand = set()
        for d in rxs:
            g = (d.get('g') or '').upper()
            if d.get('b'): cand.add(d['b'].upper())
            if g:
                cand.add(g); m = re.search(re.escape(g) + r'-[A-Z]{4}\b', (d.get('d') or '').upper())
                if m: cand.add(m.group(0))
        return any(n == c or (n.startswith(c) and n[len(c)] in ' (') or c.startswith(n + ' ') for n in under[code] for c in cand)
    catch = collections.defaultdict(list)
    for d in D.values():
        if d.get('h') and noc(d['h']): catch[(d['b'] or d['g'], d['h'])].append(d)
    unnamed = sorted({k[0] for k, rxs in catch.items() if not named_under(rxs, k[1])})
    carried = json.load(open(src('carry_forward.json'))).get('BIOSIM', {})
    second = {c for c, g in ny} | {c for c in HC if c in PBD and (carried.get(c) or {}).get('g', '').strip().lower().rstrip('-') == PBD[c].get('g')}
    q5 = [c for c in HC if c in PBD]
    grids = grid_rows()
    if grids is None: print('      plan grids are not in sources/: the grid cross-check of biosimilar names was skipped')
    else:
        named = lambda c: any(any(nrm(b) in nrm(t) for b in parse_descriptor(HC[c]['ld'])[1]) and PBD[c]['g'][-4:] in t for t in grids.get(c, []))
        alone = sorted(set(q5) - second)
        check('biosimilars: every name with no second source in the CMS and NY files is written the same way on a plan grid', all(named(c) for c in alone),
              f'{sum(named(c) for c in alone)} of {len(alone)} confirmed by brand and suffix: {" ".join(alone)}')
        ong = [c for c in q5 if c in grids]; bad = [c for c in ong if parse_descriptor(HC[c]['ld'])[1] and not named(c)]
        print(f'      plan grids print {len(ong)} of the {len(q5)} Q5 codes; brand and suffix match CMS on {len(ong) - len(bad)}' + (f'; not matched: {" ".join(bad)}' if bad else ''))
    e = PBD.get('Q5154', {}); x = PBD.get('J2357', {})
    for name, got_, want_ in [
        ('biosimilar codes / molecules', (len(bio), sum(1 for m, (ref, bs) in groups.items() if bs)), (78, 16)),
        ('biosimilar codes with no entry before the CMS descriptors were added', sum(1 for e_ in PBD.values() if e_.get('src') == 'H'), 13),
        ('medical-benefit codes searchable', len(PBD), 1305),
        ('Q5-range names: in the page / confirmed by NY or the carried-forward list / resting on the web reading alone', (len(q5), len(second), sorted(set(q5) - second)),
         (71, 59, ['Q5137', 'Q5149', 'Q5150', 'Q5154', 'Q5155', 'Q5159', 'Q5165', 'Q5166', 'Q5168', 'Q5170', 'Q5171', 'Q5173'])),
        ('Omlyclo: code, molecule, same molecule as Xolair J2357, on Healthfirst grid, on MetroPlus grid, on Part B file',
         (e.get('n'), e.get('m'), x.get('m') == e.get('m'), 'Q5154' in G['HFPA'], 'Q5154' in G['MPPA'], 'Q5154' in G['PAYB']), ('OMLYCLO', 'omalizumab', True, True, False, False)),
        ('ranibizumab group', sorted(groups['ranibizumab'][0]) + sorted(groups['ranibizumab'][1]), ['J2778', 'J2779', 'Q5124', 'Q5128', 'Q5168']),
        ('Medicare / NY Medicaid eligible: Cimerli, Byooviz, Omlyclo, Lucentis, Xolair', [(mcr(c), mcd(c)) for c in ('Q5128', 'Q5124', 'Q5154', 'J2778', 'J2357')],
         [('Yes', 'Yes'), ('Yes', 'No'), ('Not confirmed', 'No'), ('Yes', 'Yes'), ('Yes', 'Yes')]),
        ('Part D product groups on an unclassified code / not named under it on the NY list', (len(catch), unnamed), (32, [])),
        ('biosimilar codes by code alone: Medicare yes / not confirmed, NY Medicaid yes / no',
         (sum(mcr(c) == 'Yes' for c in bio), sum(mcr(c) == 'Not confirmed' for c in bio), sum(mcd(c) == 'Yes' for c in bio), sum(mcd(c) == 'No' for c in bio)), (56, 22, 53, 25)),
    ]: check('published: ' + name, got_ == want_, f'{got_}')

def main():
    B = blobs(os.path.join(HERE, '..', 'index.html'))
    G = B['common']; RX, CL = G['RX'], G['CL']
    if '--biosimilars' in sys.argv:
        check_biosimilars(G)
        print('\nRESULT (biosimilar checks only):', 'ALL CHECKS PASSED' if not FAILS else f'{len(FAILS)} FAILED: {FAILS}')
        return
    check('page carries common + both plan years', set(B) == {'common', '2026', '2027'}, str(sorted(B)))
    for y in YEARS:
        Y = B[y]
        # --- every formulary row
        want = {}
        for r in puf_rows(y, 'basic_drugs_formulary.txt'):
            want[(r['FORMULARY_ID'], r['RXCUI'])] = '|'.join([r['TIER_LEVEL_VALUE'], r['PRIOR_AUTHORIZATION_YN'], r['STEP_THERAPY_YN'], r['QUANTITY_LIMIT_YN'], r['QUANTITY_LIMIT_AMOUNT'], r['QUANTITY_LIMIT_DAYS'], r['SELECTED_DRUG_YN']])
        got = {}
        for fid, a in Y['C'].items():
            for i in range(0, len(a), 2): got[(fid, RX[a[i]])] = CL[a[i + 1]]
        bad = sum(1 for k, v in want.items() if got.get(k) != v)
        check(f'{y} formulary rows: page == CMS file', bad == 0 and len(got) == len(want), f'{len(want):,} source rows, {len(got):,} in page, {bad} mismatched')
        # --- plans
        src_p = collections.OrderedDict()
        for r in puf_rows(y, 'plan_information.txt'):
            src_p.setdefault((r['CONTRACT_ID'], r['PLAN_ID']), r)
        pg = {(p['cid'], p['pid']): p for p in Y['P']}
        badp = [k for k, r in src_p.items() if k not in pg or pg[k]['pn'] != r['PLAN_NAME'].strip() or pg[k]['fid'] != r['FORMULARY_ID'].strip() or pg[k]['pr'] != r['PREMIUM'].strip() or pg[k]['ded'] != r['DEDUCTIBLE'].strip()]
        check(f'{y} plans: name, formulary, premium, deductible', not badp and len(pg) == len(src_p), f'{len(src_p):,} plans')
        check(f'{y} every plan has a state and a formulary in the page', all(p['st'] for p in Y['P']) and sum(1 for p in Y['P'] if p['fid'] not in Y['C']) <= 1,
              f'no state: {sum(1 for p in Y["P"] if not p["st"])}, formulary not published: {sum(1 for p in Y["P"] if p["fid"] not in Y["C"])}')
        # --- county-level state check for MA plans (independent of the build's region logic)
        st = collections.defaultdict(set)
        for r in puf_rows(y, 'plan_information.txt'):
            if r['STATE'].strip(): st[(r['CONTRACT_ID'], r['PLAN_ID'])].add(r['STATE'].strip())
        bads = [k for k, s in st.items() if not s <= set(pg[k]['st'].split(','))]
        check(f'{y} plan states cover every county-level state in the file', not bads, f'{len(st):,} plans with county rows')
        ny = [p for p in Y['P'] if 'NY' in p['st'].split(',')]
        print(f'      {y}: {len(ny)} plans serve NY ({sum(1 for p in ny if p["cid"][0]=="S")} stand-alone PDPs, {sum(1 for p in ny if p["cid"][0]=="R")} regional PPOs)')
        # --- cost share, sampled
        seg = {}
        for r in puf_rows(y, 'plan_information.txt'): seg.setdefault((r['CONTRACT_ID'], r['PLAN_ID']), r['SEGMENT_ID'])
        wantc = {}
        for r in puf_rows(y, 'beneficiary_cost.txt'):
            k = (r['CONTRACT_ID'], r['PLAN_ID'])
            if seg.get(k) != r['SEGMENT_ID'] or r['COVERAGE_LEVEL'].strip() != '1' or r['DAYS_SUPPLY'].strip() != '1': continue
            t, a = r['COST_TYPE_PREF'].strip(), r['COST_AMT_PREF'].strip()
            if t in ('', '0'): t, a = r['COST_TYPE_NONPREF'].strip(), r['COST_AMT_NONPREF'].strip()
            if t in ('', '0'): continue
            wantc[f"{k[0]}|{k[1]}|{r['TIER'].strip()}"] = (t, float(a))
        badc = sum(1 for k, v in wantc.items() if k not in Y['COST'] or (Y['COST'][k].split('|')[0], float(Y['COST'][k].split('|')[1])) != v)
        check(f'{y} cost share per plan and tier', badc == 0 and len(wantc) == len(Y['COST']), f'{len(wantc):,} plan-tier values')
    # --- Part B
    pl = read_csv_table(find('section 508 version of * Medicare Part B Payment Limit File*.csv'), ('HCPCS Code',))
    badb = [r['HCPCS Code'] for r in pl if G['PAYB'].get(r['HCPCS Code'], {}).get('p') != r['Payment Limit'] or G['PAYB'][r['HCPCS Code']].get('c') != r['Co-insurance Percentage']]
    check('Part B payment limit and coinsurance for every HCPCS', not badb and len(pl) == len(G['PAYB']), f'{len(pl)} codes')
    np_ = read_csv_table(find('section 508 version of * Drugs Not Payable Under Part B*.csv'), ('HCPCS Code',))
    check('Part B not-payable list', {r['HCPCS Code'] for r in np_} == set(G['NOTPAYB']), f'{len(np_)} codes')
    # --- NYRx
    rx_ndc = load('rx_ndc.json'); em = {}
    with open(src('MedReimbDrugsFormulary.csv'), encoding='latin-1', newline='') as f:
        rd = csv.reader(f); hdr = [h.strip() for h in next(rd)]
        for row in rd:
            r = dict(zip(hdr, [c.strip() for c in row])); em[ndc11(r['NDC'])] = r['PREFERRED DRUG CODE']
    exact = [(rx, [em[n] for n in rx_ndc[rx] if n in em]) for rx in RX]
    badn = [rx for rx, v in exact if v and G['NYMC'].get(rx) not in v]
    check('NYRx status equals the eMedNY row for the drug\'s NDC', not badn, f'{sum(1 for _, v in exact if v):,} drugs with an exact NDC row; {len(G["NYMC"]):,} with a status')
    # --- figures published in the project write-up (claude/hh-coverage-lookup-tool.md). Change the document and these together.
    def um(y, cid, pid):
        p = next(p for p in B[y]['P'] if p['cid'] == cid and p['pid'] == pid); a = B[y]['C'][p['fid']]
        c = [CL[i].split('|') for i in a[1::2]]; n = len(c)
        return n, round(100 * sum(x[1] == 'Y' for x in c) / n), round(100 * sum(x[2] == 'Y' for x in c) / n), round(100 * sum(x[3] == 'Y' for x in c) / n), len({x[0] for x in c})
    ny = lambda y: sum(1 for p in B[y]['P'] if 'NY' in p['st'].split(','))
    pub = [
        ('drugs in the page', len(RX), 6201),
        ('2026 plans / formularies', (len(B['2026']['P']), len(B['2026']['C'])), (5074, 328)),
        ('2027 plans / formularies', (len(B['2027']['P']), len(B['2027']['C'])), (5034, 286)),
        ('plans serving NY 2026 / 2027', (ny('2026'), ny('2027')), (193, 199)),
        ('MetroPlus Advantage 2026: drugs, PA%, ST%, QL%, tiers', um('2026', 'H0423', '001'), (3542, 33, 1, 42, 5)),
        ('MetroPlus Platinum 2026: drugs, PA%, ST%, QL%, tiers', um('2026', 'H0423', '004'), (3455, 34, 1, 42, 1)),
        ('Healthfirst 65 Plus 2026: drugs, PA%, ST%, QL%, tiers', um('2026', 'H3359', '001'), (3379, 34, 1, 42, 5)),
        ('MetroPlus Advantage 2027: drugs, PA%, ST%, QL%, tiers', um('2027', 'H0423', '001'), (3517, 33, 1, 42, 5)),
        ('Healthfirst 65 Plus 2027: drugs, PA%, ST%, QL%, tiers', um('2027', 'H3359', '001'), (3354, 34, 1, 42, 5)),
        ('NYRx status counts Y / N / X', tuple(sum(1 for v in G['NYMC'].values() if v == k) for k in 'YNX'), (1315, 1834, 2546)),
        ('Part B codes / not payable', (len(G['PAYB']), len(G['NOTPAYB'])), (918, 7)),
        ('drugs with a HCPCS bridge from the NDC crosswalks', sum(1 for d in G['D'].values() if d.get('h') and not d.get('hn')), 848),
        ('NY PAD codes / fee-schedule codes', (len(G['NYSMED']), len(G['NYSFS'])), (792, 911)),
        ('Healthfirst / MetroPlus medical PA codes', (len(G['HFPA']), len(G['MPPA'])), (352, 258)),
    ]
    for name, got_, want_ in pub: check('published: ' + name, got_ == want_, f'{got_}')
    check_biosimilars(G)
    print('\nRESULT:', 'ALL CHECKS PASSED' if not FAILS else f'{len(FAILS)} FAILED: {FAILS}')

if __name__ == '__main__':
    main()
