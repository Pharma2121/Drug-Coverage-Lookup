"""Stage 4 - plan overlays for Healthfirst and MetroPlus (lines of business CMS does not publish).

Inputs  : Healthfirst Leaf / Leaf Premier / Essential Plan comprehensive drug lists (2026, 2027)   [PDF]
          MetroPlus Marketplace (QHP / Gold / GoldCare) and Essential Plan formularies             [PDF]
          Healthfirst "Medications Requiring Prior Authorization Under the Medical Benefit" grid   [PDF]
          MetroPlus "Physician Administered Drugs Requiring Prior Authorization" grids (3 LOBs)    [PDF]
          out/drugs.json (stage 2)
Outputs : out/plans.json
            FORM[key]  = {rx: {RxCUI: 'tier|flags'}, bn: {BRAND: 'tier|flags'}, label, eff, n}
            HFPA[code] = {s: P|N|X, a: 1 (PA grid), l: LOB text}
            MPPA[code] = {s: P|N, mcr/mcd/qhp: 1 where that grid requires PA}
The pharmacy formularies are matched to RxCUIs here, at build time, so the page does no name guessing.
Matching is best-effort (ingredient set or brand, then dose form and strength) and is labelled as such in the page.
"""
import collections, glob
from common import *
from formulary_match import parse_formulary, match

UNCLASSIFIED = {'C9399', 'J3490', 'J3590', 'J7599', 'J7999', 'J8499', 'J8999', 'J9999', 'J7699', 'J7799'}

def pref_list_hf(doc):
    """Healthfirst 'List of Preferred and Non-Preferred Products' pages -> {code: set(statuses)}."""
    st = collections.defaultdict(set)
    for pg in doc:
        t = pg.get_text()
        if 'HCPCS Status' not in t: continue
        pend = []
        for line in t.split('\n'):
            line = line.strip()
            m = re.match(r'^(Preferred|Non-preferred)\b', line, re.I)
            if m:
                for c in pend: st[c].add('P' if m.group(1).lower() == 'preferred' else 'N')
                pend = []
                continue
            if re.match(r'^[A-Z]\d{4}[,\s]*', line): pend += re.findall(r'\b([A-Z]\d{4})\b', line)
    return st

def grid_tables(doc, first_page=0):
    for pg in list(doc)[first_page:]:
        for tb in pg.find_tables().tables:
            for row in tb.extract():
                yield [(c or '').replace('\n', ' ').strip() for c in row]

def main():
    import pymupdf
    D = load('drugs.json')['D']
    FORM = {}
    for key, pat, label in (('hf26', '*November-2026-Formulary-QHP-EP*.pdf', 'Healthfirst Leaf / Essential Plan 2026'),
                            ('hf27', '*January-2027-Formulary-QHP-EP*.pdf', 'Healthfirst Leaf / Essential Plan 2027'),
                            ('mpq', 'QHP_Formulary-Document_*.pdf', 'MetroPlus Marketplace / Gold / GoldCare'),
                            ('mpe', 'Marketplace_EP_Formulary-Document_*.pdf', 'MetroPlus Essential Plan')):
        pdf = os.path.basename(sorted(glob.glob(src(pat)))[-1])
        entries, eff = parse_formulary(src(pdf))
        rxm, bn, stats = match(entries, D)
        FORM[key] = {'rx': rxm, 'bn': bn, 'label': label, 'eff': eff, 'n': len(entries), 'file': pdf}
        print(f'{key}: {len(entries)} entries ({eff}) -> {len(rxm)} RxCUIs, {len(bn)} brands | tiers {dict(collections.Counter(e["tier"] for e in entries))}')
        print('     ', dict(stats))
        save(f'_entries_{key}.json', [{'name': e['name'], 'tier': e['tier'], 'req': e['req']} for e in entries])

    # ---- Healthfirst medical-benefit grid
    hf = pymupdf.open(src(os.path.basename(sorted(glob.glob(src('Prior-Authorization-Medical-Benefit-Grid*.pdf')))[-1])))
    rev = re.search(r'LAST REVISED\s+(\S+)', hf[0].get_text())
    st = pref_list_hf(hf)
    HFPA = {}
    first_grid = next(i for i, p in enumerate(hf) if all(w in p.get_text() for w in ('Delegated', 'LOB', 'Billable')))
    for row in grid_tables(hf, first_grid):
        codes = []
        for c in row:
            if re.fullmatch(r'(?:[A-Z]\d{4}[\s,;/]*)+', c or ''): codes += re.findall(r'[A-Z]\d{4}', c)
        if not codes: continue
        lob = next((c for c in reversed(row) if re.search(r'(65\+|IBP|MMC|QHP|CHPlus|PWP)', c or '')), '')
        for c in codes:
            e = HFPA.setdefault(c, {'a': 1})
            if lob and 'l' not in e: e['l'] = re.sub(r'\s+', ' ', lob.replace('- ', '-'))[:90]
    for c, s in st.items():
        if c in UNCLASSIFIED: continue
        HFPA.setdefault(c, {})['s'] = 'X' if len(s) > 1 else next(iter(s))
    print(f'HFPA: {len(HFPA)} codes (revised {rev.group(1) if rev else "?"}) | PA grid {sum(1 for v in HFPA.values() if v.get("a"))} | status {dict(collections.Counter(v.get("s", "-") for v in HFPA.values()))}')

    # ---- MetroPlus physician-administered-drug grids
    MPPA, upd = {}, ''
    for lobk, pat in (('mcr', 'PAD-Auth-Grid_-Medicare.pdf'), ('mcd', 'PAD-Auth-Grid_Medicaid.pdf'), ('qhp', 'PAD-Auth-Grid_QHP-EP-CHP-Gold.pdf')):
        doc = pymupdf.open(src(pat))
        m = re.search(r'Updated\s+(\S+)', doc[0].get_text()); upd = m.group(1) if m else upd
        n = 0
        for row in grid_tables(doc):
            cells = [c for c in row if c]
            if not cells: continue
            m = re.match(r'^([A-Z]\d{4}|\d{5})\b', cells[0])
            if not m: continue
            code = m.group(1); e = MPPA.setdefault(code, {}); e[lobk] = 1; n += 1
            stat = next((c for c in cells[1:] if re.match(r'^(Non-?\s?Preferred|Preferred)\b', c, re.I)), '')
            if stat and code not in UNCLASSIFIED:
                s = 'N' if re.match(r'^Non', stat, re.I) else 'P'
                e['s'] = s if e.get('s', s) == s else 'X'
        print(f'   MetroPlus {lobk}: {n} codes')
    print(f'MPPA: {len(MPPA)} codes (updated {upd}) | status {dict(collections.Counter(v.get("s", "-") for v in MPPA.values()))}')
    save('plans.json', {'FORM': FORM, 'HFPA': HFPA, 'MPPA': MPPA, 'meta': {'hf_grid_rev': rev.group(1) if rev else '', 'mp_grid_upd': upd}})

if __name__ == '__main__':
    main()
