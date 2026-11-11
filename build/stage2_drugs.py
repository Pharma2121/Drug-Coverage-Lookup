"""Stage 2 - drug dictionary, NY Medicaid (NYRx) status, unit prices and the Part D -> HCPCS bridge.

Inputs  : out/partd.json, out/rx_ndc.json (stage 1)
          CMS Formulary Reference Files (CY26, CY27)            -> names, brand, strength, dose form
          eMedNY MedReimbDrugsFormulary.csv                       -> NYRx preferred / non-preferred / covered
          CMS ASP / AWP / OPPS / PrEP NDC-HCPCS crosswalks        -> HCPCS for Part D drugs also billable as medical
          NYS DOH List of Physician Administered Drugs (PDF)     -> second NDC-HCPCS source, NY PAD attributes
          sources/partd_2026_price_ndc_median.csv                 -> median plan-reported unit cost per NDC (Q3 2026)
          sources/carry_forward.json             -> names only, for RxCUIs CMS no longer lists in an FRF
Outputs : out/drugs.json (D, NYMC, DP), out/pad.json (parsed PAD list), out/xwalk.json (HCPCS -> crosswalk rows)
"""
import collections, sys, glob
from common import *

def read_csv_table(name, first_cols):
    """Read a CMS '508' CSV that has free-text preamble rows before the real header."""
    rows, hdr = [], None
    with open(src(name), encoding='latin-1', newline='') as f:
        for row in csv.reader(f):
            if hdr is None:
                if row and row[0].strip() in first_cols:
                    hdr = [c.strip() for c in row]
                continue
            if not row or not row[0].strip(): continue
            rows.append(dict(zip(hdr, [c.strip() for c in row])))
    return rows

def find(pattern):
    g = sorted(glob.glob(src(pattern)))
    if not g: raise SystemExit('missing source: ' + pattern)
    return os.path.basename(g[-1])

def crosswalks():
    """All four CMS crosswalks -> list of {code, sd, ndc, name, dose, src}."""
    out_rows = []
    for pat, tag in (('section 508 version of * ASP NDC-HCPCS Crosswalk*.csv', 'ASP'),
                     ('Section 508 Version of * AWP NDC-HCPCS Crosswalk*.csv', 'AWP'),
                     ('section 508 version of * OPPS NDC-HCPCS Crosswalk*.csv', 'OPPS'),
                     ('Section 508 version of * PrEP NDC-HCPCS Crosswalk*.csv', 'PrEP')):
        for r in read_csv_table(find(pat), ('_2026_CODE', '_2027_CODE', 'HCPCS Code', 'HCPCS')):
            k = {kk.upper(): v for kk, v in r.items()}
            code = k.get('_2026_CODE') or k.get('_2027_CODE') or k.get('HCPCS CODE') or k.get('HCPCS')
            ndc = k.get('NDC') or k.get('NDC OR ALTERNATE ID') or ''
            sd = k.get('SHORT DESCRIPTION') or k.get('SHORT DESCRIPTOR') or ''
            out_rows.append({'code': code.strip(), 'sd': sd, 'ndc': ndc11(ndc) if re.match(r'^[\d-]+$', ndc) else '',
                             'name': k.get('DRUG NAME', ''), 'dose': k.get('HCPCS DOSAGE', ''), 'src': tag})
    return out_rows

def pad_list():
    """NYS DOH List of Physician Administered Drugs -> {code: {n, do, mr, pa, drugs:[...], ndcs:[...]}} + effective date."""
    import pymupdf
    doc = pymupdf.open(src('pad-drug-list.pdf'))
    txt = '\n'.join(p.get_text() for p in doc)
    eff = re.search(r'EFFECTIVE\s+(\d{2}/\d{2}/\d{4})', txt)
    pad, cur = collections.OrderedDict(), None
    for line in txt.split('\n'):
        m = re.match(r'\s*PROCEDURE CODE \(J-CODE\):\s*(\S+)\s+PROCEDURE NAME:\s*(.*?)\s+HCPCS CODE DOSAGE DESCRIPTION:\s*(.*)$', line)
        if m:
            cur = pad.setdefault(m.group(1), {'n': m.group(2).strip(), 'do': m.group(3).strip(), 'mr': 0, 'pa': 0, 'drugs': [], 'ndcs': []})
            continue
        m = re.match(r'\s*PROCEDURE MANUAL REVIEW CODE:\s*(.*?)\s+PA REQUIRED CODE:\s*(.*)$', line)
        if m and cur is not None:
            cur['mr'] = 0 if m.group(1).strip().upper().startswith('NOT REQUIRED') else 1
            cur['pa'] = 0 if 'NOT REQUIRED' in m.group(2).upper() else 1
            cur['mr_txt'], cur['pa_txt'] = m.group(1).strip(), m.group(2).strip()
            continue
        m = re.match(r'\s*NDC:\s*(\d{11})\s+DRUG NAME:\s*(.*?)\s+GENERIC NAME:\s*(.*?)\s+BILLING UNIT TYPE:', line)
        if m and cur is not None:
            cur['ndcs'].append(m.group(1))
            nm = m.group(2).strip()
            if nm and nm not in cur['drugs']: cur['drugs'].append(nm)
            g = m.group(3).strip()
            if g and 'g' not in cur: cur['g'] = g
    return {'eff': eff.group(1) if eff else '', 'codes': pad}

def main():
    partd = load('partd.json'); RX = partd['RX']; rx_ndc = load('rx_ndc.json')
    prev = json.load(open(src('carry_forward.json')))['D']

    # ---- names: newest FRF wins, then the other year, then the previous build
    frf = {}
    for pat in ('CY26 FRF_*.csv', 'CY27 FRF_*.csv'):
        with open(src(find(pat)), encoding='latin-1', newline='') as f:
            for r in csv.DictReader(f):
                frf[r['RxCUI'].strip()] = r
    D, miss, carried = {}, [], 0
    for rx in RX:
        r = frf.get(rx)
        if r:
            D[rx] = {'b': r['Related BN'].strip().upper(), 'd': r['RxNorm Description'].strip().upper(),
                     's': r['Related SCDC'].strip().upper(), 'f': r['Related DF'].strip().upper(),
                     'g': (r.get('RxNorm Ingredient') or '').strip().upper()}
        elif rx in prev and prev[rx].get('d'):
            p = prev[rx]; D[rx] = {'b': p.get('b', ''), 'd': p['d'], 's': p.get('s', ''), 'f': p.get('f', ''), 'g': ''}; carried += 1
        else:
            D[rx] = {'b': '', 'd': '', 's': '', 'f': '', 'g': ''}; miss.append(rx)
    for d in D.values():                      # ingredient label: FRF column where present, else the strength text without the numbers
        g = d['g'].replace('/', ' / ') if d['g'] and ' / ' not in d['g'] else d['g']
        if not g and d['s']:
            g = ' / '.join(re.sub(r'\s+[\d.].*$', '', x.strip()) for x in d['s'].split(' / '))
        d['g'] = re.sub(r'\s+', ' ', g).strip()
    print(f'D: {len(D)} drugs | named from FRF {len(D)-carried-len(miss)} | name carried from previous build {carried} | unnamed {len(miss)}')

    # ---- HCPCS bridge: exact NDC in a CMS crosswalk, then same labeler-product (9 digits), then the NY PAD list
    xw = crosswalks(); pad = pad_list()
    idx = [collections.defaultdict(set) for _ in range(4)]
    for r in xw:
        if r['ndc']:
            idx[0][r['ndc']].add(r['code']); idx[1][r['ndc'][:9]].add(r['code'])
    for code, v in pad['codes'].items():
        for n in v['ndcs']:
            idx[2][n].add(code); idx[3][n[:9]].add(code)
    how = collections.Counter()
    for rx in RX:
        for i, key in ((0, lambda n: n), (1, lambda n: n[:9]), (2, lambda n: n), (3, lambda n: n[:9])):
            c = set()
            for n in rx_ndc.get(rx, ()): c |= idx[i].get(key(n), set())
            if c:
                D[rx]['h'] = sorted(c)[0]; how[('CMS crosswalk NDC', 'CMS crosswalk labeler-product', 'NY PAD NDC', 'NY PAD labeler-product')[i]] += 1
                break
        else:
            D[rx]['h'] = ''
    print('HCPCS bridge:', sum(how.values()), dict(how))

    # ---- NYRx: the PUF's NDC for each RxCUI looked up in the eMedNY reimbursable-drug file
    em, em9 = {}, collections.defaultdict(list)
    with open(src('MedReimbDrugsFormulary.csv'), encoding='latin-1', newline='') as f:
        rd = csv.reader(f); hdr = [h.strip() for h in next(rd)]
        for row in rd:
            r = dict(zip(hdr, [c.strip() for c in row])); n = ndc11(r['NDC'])
            em[n] = r; em9[n[:9]].append(r)
    rank = {'Y': 3, 'X': 2, 'N': 1}
    NYMC, NYPA, hown = {}, {}, collections.Counter()
    for rx in RX:
        hits = [em[n] for n in rx_ndc.get(rx, ()) if n in em]; tag = 'exact NDC'
        if not hits:
            hits = [r for n in rx_ndc.get(rx, ()) for r in em9.get(n[:9], ())]; tag = 'labeler-product'
        hits = [h for h in hits if h['PREFERRED DRUG CODE'] in rank]
        if hits:
            best = max(hits, key=lambda h: rank[h['PREFERRED DRUG CODE']])
            NYMC[rx] = best['PREFERRED DRUG CODE']; hown[tag] += 1
            if best['PA'] in ('N', 'G'): NYPA[rx] = best['PA']
    print('NYRx status:', len(NYMC), dict(hown), dict(collections.Counter(NYMC.values())), '| PA flags', dict(collections.Counter(NYPA.values())))

    # ---- unit price: median 30-day unit cost across all plans, per NDC, from the quarterly pricing file
    price = {}
    pf = src('partd_2026_price_ndc_median.csv')
    if os.path.exists(pf):
        with open(pf) as f:
            for r in csv.DictReader(f): price[r['ndc']] = float(r['median_unit_cost'])
    DP = {}
    for rx in RX:
        v = [price[n] for n in rx_ndc.get(rx, ()) if n in price]
        if v: DP[rx] = round(sorted(v)[len(v)//2], 2)
    print('DP (unit price):', len(DP))

    save('drugs.json', {'D': D, 'NYMC': NYMC, 'NYPA': NYPA, 'DP': DP, 'unnamed': miss})
    save('pad.json', pad)
    save('xwalk.json', xw)

if __name__ == '__main__':
    main()
