"""Reconcile the finished index.html against the raw source files. Run after stage 5.
Every figure the page can show for Part D and Part B is re-read from the page's own embedded data and compared with the source rows."""
import base64, gzip, random, collections
from common import *
from stage2_drugs import read_csv_table, find

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

def main():
    B = blobs(os.path.join(HERE, '..', 'index.html'))
    G = B['common']; RX, CL = G['RX'], G['CL']
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
        ('drugs with a HCPCS bridge', sum(1 for d in G['D'].values() if d.get('h')), 848),
        ('NY PAD codes / fee-schedule codes', (len(G['NYSMED']), len(G['NYSFS'])), (792, 911)),
        ('Healthfirst / MetroPlus medical PA codes', (len(G['HFPA']), len(G['MPPA'])), (352, 258)),
    ]
    for name, got_, want_ in pub: check('published: ' + name, got_ == want_, f'{got_}')
    print('\nRESULT:', 'ALL CHECKS PASSED' if not FAILS else f'{len(FAILS)} FAILED: {FAILS}')

if __name__ == '__main__':
    main()
