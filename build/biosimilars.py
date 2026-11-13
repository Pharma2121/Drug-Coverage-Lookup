"""Biosimilars: give every biosimilar a searchable entry, its molecule, and a link to its reference product.

Stage 5 calls enrich() on the assembled page data just before it is embedded.

Why this exists: the searchable list of medical-benefit drugs is built from the CMS Part B payment file, the CMS
NDC-HCPCS crosswalks and the two NY Medicaid lists. A biosimilar that none of those four files names yet (a code
CMS issued but that has no payment limit, for example) had no entry, even when a plan's authorization grid listed
its code. And an entry whose only description was "Inj, cimerli, 0.1 mg" could not be found by typing "ranibizumab".

Source: sources/hcpcs_biosimilar_codes.csv - the CMS HCPCS Level II long descriptors for the biosimilar code range
(Q5098 and up), e.g. "Injection, ranibizumab-eqrn (cimerli), biosimilar, 0.1 mg".

What enrich() adds
  PBD[code]            an entry for every active biosimilar code that had none (src = 'H')
  PBD[code].bio = 1    on every biosimilar code
  PBD[code].g          the biosimilar's own name, e.g. "ranibizumab-eqrn"
  PBD[code].m          the molecule, e.g. "ranibizumab" - also set on the reference product and other codes for the
                       same molecule, found as a whole word in the code's official description
  PBD[code].ld         the CMS long descriptor (when it differs from .sd);  .eff / .end  the code's start and end dates
  PBD[code].alt        every brand the descriptor names ("jubbonti/wyost")
  D[rx].h, D[rx].hn    a Part D product with no crosswalk code is linked to a biosimilar code when the CMS
                       descriptor names its brand, the ingredient matches, and that brand has exactly one code
  BIOSIM[code]         brand / generic label for every biosimilar code (kept for the older search path)
"""
import csv, re
from common import src

SUFFIX = re.compile(r'-[a-z]{4}$')
# Fragments that mark a different product which merely contains the molecule's name (conjugates, combinations,
# differently named versions). A code whose description has one of these is left out of the molecule group.
NOT_SAME = ('emtansine', 'deruxtecan', 'ziv-', 'ado-', 'fam-', 'tbo-', 'tbo ', 'vedotin', 'tesirine', 'govitecan',
            'ozogamicin', 'tiuxetan', 'pegol', 'peg-', 'methoxy polyethylene', 'pertuzu')

def nrm(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())

def base(generic):
    return SUFFIX.sub('', (generic or '').strip().lower())

def fmt_date(s):
    return f'{int(s[4:6])}/{int(s[6:8])}/{s[:4]}' if s and len(s) == 8 else ''

def load_hcpcs():
    with open(src('hcpcs_biosimilar_codes.csv'), newline='', encoding='utf-8') as f:
        return {r['HCPCS']: {'ld': r['LONG_DESCRIPTION'].strip(), 'add': r['ADD_DATE'].strip(), 'term': r['TERM_DATE'].strip()} for r in csv.DictReader(f)}

def parse_descriptor(ld):
    """'Injection, denosumab-bbdz (jubbonti/wyost), biosimilar, 1 mg' -> ('denosumab-bbdz', ['jubbonti', 'wyost'], '1 mg', '')"""
    m = re.match(r'Injection,\s+([a-z][a-z ]*?-[a-z]{4})\b', ld)
    brands = []
    for p in re.findall(r'\(([^)]+)\)', ld):
        if not p.lower().startswith('for '): brands += [b.strip() for b in p.split('/') if b.strip()]
    route = next((r for r in ('subcutaneous', 'intravenous') if re.search(r',\s*' + r + r'\b', ld)), '')
    return (m.group(1) if m else ''), brands, ld.rsplit(',', 1)[-1].strip(), route

def ny_generic(desc):
    m = re.match(r'\s*INJ(?:ECTION)?[,.]?\s+([A-Z][A-Z ]*?-[A-Z]{4})\b', (desc or '').upper())
    return m.group(1).lower() if m else ''

def enrich(G, HC):
    PBD, BIO, D = G['PBD'], G['BIOSIM'], G['D']
    PAYB, NYSMED, NYSFS, HF, MP = G['PAYB'], G['NYSMED'], G['NYSFS'], G['HFPA'], G['MPPA']
    rep = {'added': [], 'flagged': [], 'flagged_by_rule': [], 'skipped_ended': [], 'curated_differs': [], 'ny_differs': [],
           'no_generic': [], 'bridged': [], 'bridge_ambiguous': [], 'groups': {}}
    descs = lambda code: [x for x in ((PAYB.get(code) or {}).get('sd'), (NYSMED.get(code) or {}).get('n'), (NYSFS.get(code) or {}).get('d'), (PBD.get(code) or {}).get('sd')) if x]

    # 1. every biosimilar code CMS has issued
    brand_codes = {}
    for code, h in sorted(HC.items()):
        generic, brands, dose, route = parse_descriptor(h['ld'])
        e = PBD.get(code)
        if e is None:
            if h['term'] and not (code in HF or code in MP or code in BIO): rep['skipped_ended'].append(code); continue
            if not generic: rep['no_generic'].append(code); continue
            e = PBD[code] = {'n': (brands[0] if brands else generic).upper(), 'sd': h['ld'], 'do': dose.upper(), 'src': 'H'}
            rep['added'].append(code)
        elif not e.get('bio'): rep['flagged'].append(code)
        e['bio'] = 1; e['eff'] = fmt_date(h['add'])
        if e['sd'] != h['ld']: e['ld'] = h['ld']
        if h['term']: e['end'] = fmt_date(h['term'])
        if route: e['rt'] = route
        if generic: e['g'] = generic; e['m'] = base(generic)
        else: rep['no_generic'].append(code)
        known = [nrm(e['n'])] + [nrm(a) for a in e.get('alt', [])]
        extra = [b.upper() for b in brands if not any(nrm(b) in k for k in known)]
        if extra: e['alt'] = e.get('alt', []) + extra
        if not h['term']:
            for b in brands: brand_codes.setdefault(nrm(b), set()).add(code)
        # cross-checks against the two other places a generic name is written down
        cur = (BIO.get(code) or {}).get('g', '').strip().lower().rstrip('-')
        if generic and re.fullmatch(r'[a-z ]+-[a-z]{4}', cur) and cur != generic: rep['curated_differs'].append((code, cur, generic))
        for dsc in ((NYSMED.get(code) or {}).get('n'), (NYSFS.get(code) or {}).get('d')):
            ng = ny_generic(dsc)
            if ng and generic and ng != generic: rep['ny_differs'].append((code, ng, generic))
        BIO[code] = {'b': (BIO.get(code) or {}).get('b') or (brands[0].title() if brands else ''), 'g': generic.capitalize()}

    mols = sorted({e['m'] for e in PBD.values() if e.get('bio') and e.get('m')}, key=len, reverse=True)

    # 2. temporary Q-codes outside the Q5 range that carry a suffixed name of one of those molecules (Q9996-Q9999, Q0234 ...)
    for code, e in sorted(PBD.items()):
        if e.get('bio') or not code.startswith('Q'): continue
        text = ' | '.join(descs(code)).lower()
        for m in mols:
            hit = re.search(r'(?<![a-z\-])' + re.escape(m) + r'-([a-z]{4})(?![a-z])', text)
            if hit:
                e['bio'] = 1; e['g'] = m + '-' + hit.group(1); e['m'] = m
                rep['flagged_by_rule'].append((code, e['n'], e['g'])); break

    # 3. reference products and other codes for the same molecule
    for code, e in PBD.items():
        if e.get('bio'): continue
        text = ' | '.join(descs(code)).lower()
        if not text or any(t in text for t in NOT_SAME): continue
        for m in mols:
            if re.search(r'(?<![a-z\-])' + re.escape(m) + r'(?![a-z])', text):
                e['m'] = m; break

    # 4. Part D products with no crosswalk code, linked by the brand name in the CMS descriptor
    for rx, d in sorted(D.items()):
        if d.get('h') or not d.get('b'): continue
        codes = brand_codes.get(nrm(d['b']))
        if not codes: continue
        if len(codes) > 1: rep['bridge_ambiguous'].append((d['b'], sorted(codes))); continue
        code = next(iter(codes))
        if (d.get('g') or '').strip().lower() != PBD[code].get('m'): continue
        d['h'] = code; d['hn'] = 1
        rep['bridged'].append((rx, d['b'], code))

    for code, e in sorted(PBD.items()):
        if e.get('m'): rep['groups'].setdefault(e['m'], {'ref': [], 'bio': []})['bio' if e.get('bio') else 'ref'].append(f"{code} {e['n']}")
    return rep

def print_report(rep):
    print(f"  biosimilar codes: {sum(len(g['bio']) for g in rep['groups'].values())} in {len(rep['groups'])} molecule groups")
    print(f"  entries added from the CMS descriptors: {len(rep['added'])}  {' '.join(rep['added'])}")
    print(f"  existing entries newly flagged: {' '.join(rep['flagged']) or 'none'}")
    print(f"  flagged by rule (non-Q5 code, suffixed name): {', '.join(f'{c} {n} {g}' for c, n, g in rep['flagged_by_rule']) or 'none'}")
    print(f"  ended codes left out (no data anywhere): {' '.join(rep['skipped_ended']) or 'none'}")
    print(f"  Part D products linked by brand name: {len(rep['bridged'])}  {sorted({(b, c) for _, b, c in rep['bridged']})}")
    if rep['bridge_ambiguous']: print(f"  brand names with more than one code (not linked): {sorted({(b, tuple(c)) for b, c in rep['bridge_ambiguous']})}")
    for k, lab in (('curated_differs', 'carried-forward name differs from CMS'), ('ny_differs', 'NY description differs from CMS'), ('no_generic', 'no generic name parsed')):
        if rep[k]: print(f"  CHECK {lab}: {rep[k]}")
