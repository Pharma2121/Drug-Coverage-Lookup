"""Stage 3 - medical-benefit data: Medicare Part B and NY Medicaid physician-administered drugs.

Inputs  : CMS Medicare Part B Payment Limit File + Drugs Not Payable Under Part B (quarterly)
          out/xwalk.json, out/pad.json (stage 2)
          eMedNY Physician Manual Fee Schedule, Section 3 - Drugs (xls)
          sources/carry_forward.json  -> brand / generic labels for biosimilar Q-codes already curated
Outputs : out/medical.json (PAYB, NOTPAYB, PBD, BIOSIM, NYSMED, PADN, NYSFS + effective dates)
"""
import collections, glob
from common import *
from stage2_drugs import read_csv_table, find

def clean_name(s):
    s = re.sub(r'\([^)]*\)', ' ', s or '')          # drop "(2025/2026)", "(Preservative Free)" ...
    s = re.sub(r'[®™*]', '', s)
    return re.sub(r'\s+', ' ', s).strip().upper()

FORM_WORDS = r'(VIAL|VL|SYRINGE|SYRNG|SYR|PEN|AUTOINJECTOR|AUTOINJCT|AUTO-INJECTOR|KIT|CARTRIDGE|CARTRIDG|INJECTION|INJ|SOLUTION|SOLN|AMPUL|AMPULE|BAG|IMPLANT|POWDER|SUSP|EMULSION|PREP|TAB|TABLET|CAPSULE|CAP|NEONATAL|PF|PRESERVATIVE-FREE|PRSV-FREE|SDV|MDV|SD|MD)'
def pad_base(nm):
    """PAD drug names carry strength and package text; reduce to the matchable product name."""
    b = re.sub(r'\s+\d.*$', '', nm.upper()).strip()
    b2 = b
    while True:
        n = re.sub(r'\s+' + FORM_WORDS + r'$', '', b2).strip()
        if n == b2: break
        b2 = n
    return b, b2

def main():
    prev = json.load(open(src('carry_forward.json')))
    xw = load('xwalk.json'); pad = load('pad.json')

    # ---- Medicare Part B payment limits
    plf = find('section 508 version of * Medicare Part B Payment Limit File*.csv')
    eff = ''
    with open(src(plf), encoding='latin-1') as f:
        for line in f:
            m = re.search(r'Effective\s+(\w+ \d+, \d{4})\s+through\s+(\w+ \d+, \d{4})', line, re.I)
            if m: eff = f'{m.group(1)} - {m.group(2)}'; break
    PAYB = {}
    for r in read_csv_table(plf, ('HCPCS Code',)):
        code = r['HCPCS Code']
        e = {'sd': r['Short Description'], 'do': r['HCPCS Code Dosage'], 'p': r['Payment Limit'], 'c': r['Co-insurance Percentage']}
        if r.get('Notes'): e['nt'] = r['Notes'][:140]
        PAYB[code] = e
    NOTPAYB = {}
    for r in read_csv_table(find('section 508 version of * Drugs Not Payable Under Part B*.csv'), ('HCPCS Code',)):
        NOTPAYB[r['HCPCS Code']] = {'m': r['Manufacturer'].strip(), 'ld': r['Long Description']}
    print(f'PAYB {len(PAYB)} codes ({eff}) | NOTPAYB {len(NOTPAYB)}')

    # ---- NY Medicaid physician drug fee schedule
    import xlrd
    wb = xlrd.open_workbook(src('Physician_Manual_Fee_Schedule_Sect3.xls')); sh = wb.sheet_by_index(0)
    fs_eff, NYSFS, hdr_row = '', {}, None
    for i in range(sh.nrows):
        row = [str(c).strip() for c in sh.row_values(i)]
        if hdr_row is None:
            m = re.search(r'Effective Date:\s*(.*)$', row[0])
            if m: fs_eff = m.group(1).strip()
            if row[0].upper() == 'CODE': hdr_row = [c.upper().strip() for c in row]
            continue
        code = row[0]
        if re.match(r'^\d+\.0$', code): code = code[:-2]
        if not re.match(r'^[A-Z0-9]{5}$', code): continue
        r = dict(zip(hdr_row, row))
        e = {'d': r.get('DESCRIPTION', '')}
        if r.get('BR', '').upper() == 'BR': e['br'] = 1
        if r.get('PA', '') not in ('', '0', '0.0'): e['pa'] = 1
        NYSFS[code] = e
    print(f'NYSFS {len(NYSFS)} codes (effective {fs_eff}) | BR {sum(1 for v in NYSFS.values() if v.get("br"))} | PA {sum(1 for v in NYSFS.values() if v.get("pa"))}')

    # ---- NY PAD list
    NYSMED, PADN = {}, {}
    for code, v in pad['codes'].items():
        bases = []
        for nm in v['drugs']:
            b, b2 = pad_base(nm)
            for x in (b, b2):
                if x and x not in bases: bases.append(x)
                if x: PADN.setdefault(x, code)
        NYSMED[code] = {'n': v['n'], 'pa': v['pa'], 'mr': v['mr'], 'd': bases[:8]}
        if v.get('do'): NYSMED[code]['do'] = v['do']
    print(f'NYSMED {len(NYSMED)} codes (effective {pad["eff"]}) | PA {sum(v["pa"] for v in NYSMED.values())} | manual review {sum(v["mr"] for v in NYSMED.values())} | PADN names {len(PADN)}')

    # ---- biosimilar Q-codes: keep curated labels, add codes new to this quarter
    BIOSIM = dict(prev.get('BIOSIM', {}))
    names = collections.defaultdict(list)
    for r in xw:
        nm = clean_name(r['name'])
        if nm and nm not in names[r['code']]: names[r['code']].append(nm)
    added = []
    for code in sorted(set(PAYB) | set(names)):
        if not re.match(r'^Q5\d{3}$', code) or code in BIOSIM: continue
        sd = (PAYB.get(code) or {}).get('sd') or next((r['sd'] for r in xw if r['code'] == code), '')
        if not re.search(r'bio|biosim', sd, re.I) and not re.search(r'-[a-z]{4}\b', sd): continue
        b = ' / '.join(n.title() for n in names.get(code, [])[:2]) or code
        BIOSIM[code] = {'b': b, 'g': sd}; added.append(code)
    print(f'BIOSIM {len(BIOSIM)} codes | new this build: {added}')

    # ---- searchable medical-benefit dictionary
    PBD = {}
    sd_x = {}
    for r in xw: sd_x.setdefault(r['code'], (r['sd'], r['dose']))
    for code in sorted(set(PAYB) | set(names) | set(NYSMED) | set(NYSFS)):
        nlist = list(names.get(code, []))
        for b in (NYSMED.get(code) or {}).get('d', []):
            if b not in nlist and not any(b.startswith(x) or x.startswith(b) for x in nlist): nlist.append(b)
        e = {}
        if nlist:
            e['n'] = nlist[0]
            if len(nlist) > 1: e['alt'] = nlist[1:7]
        if code in PAYB:
            e['sd'] = PAYB[code]['sd']
            if PAYB[code]['do']: e['do'] = PAYB[code]['do']
        elif code in sd_x:
            e['sd'] = sd_x[code][0]
            if sd_x[code][1]: e['do'] = sd_x[code][1]
        elif code in NYSMED:
            e['sd'] = NYSMED[code]['n'][:60]
            if NYSMED[code].get('do'): e['do'] = NYSMED[code]['do']
        else:
            e['sd'] = NYSFS[code]['d']
        if 'n' not in e:
            e['n'] = (BIOSIM.get(code) or {}).get('b', '').upper() or e['sd'][:38].upper()
            if code not in PAYB and code not in names and code not in NYSMED: e['ny'] = 1
        if code in BIOSIM: e['bio'] = 1
        PBD[code] = e
    print(f'PBD {len(PBD)} codes | with brand name {sum(1 for c in PBD if names.get(c) or (NYSMED.get(c) or {}).get("d"))} | fee-schedule only {sum(1 for v in PBD.values() if v.get("ny"))}')

    save('medical.json', {'PAYB': PAYB, 'NOTPAYB': NOTPAYB, 'PBD': PBD, 'BIOSIM': BIOSIM, 'NYSMED': NYSMED, 'PADN': PADN, 'NYSFS': NYSFS,
                          'meta': {'partb_eff': eff, 'partb_file': plf, 'nysfs_eff': fs_eff, 'pad_eff': pad['eff']}})

if __name__ == '__main__':
    main()
