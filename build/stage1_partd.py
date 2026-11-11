"""Stage 1 - Medicare Part D plans, formularies and cost sharing for each plan year.

Inputs  : sources/partd_<year>.zip (CMS Prescription Drug Plan Formulary PUF text files)
Outputs : out/partd.json  -> RX (drug index), CL (coverage-limit codes), per-year P / C / COST
          out/rx_ndc.json -> RxCUI -> representative NDC(s) as published in the PUF
"""
import collections, sys
from common import *

def regions(year):
    ma, pdp, names = collections.defaultdict(set), collections.defaultdict(set), set()
    for r in puf_rows(year, 'geographic_locator.txt'):
        st = STATE_ABBR.get(r['STATENAME'].strip())
        if not st:
            names.add(r['STATENAME'].strip()); continue
        if r['MA_REGION_CODE'].strip():  ma[r['MA_REGION_CODE'].strip()].add(st)
        if r['PDP_REGION_CODE'].strip(): pdp[r['PDP_REGION_CODE'].strip()].add(st)
    if names: print('  ! unmapped state names:', sorted(names))
    return ma, pdp

def plans(year):
    ma, pdp = regions(year)
    P, states, first_seg = collections.OrderedDict(), collections.defaultdict(set), {}
    for r in puf_rows(year, 'plan_information.txt'):
        k = (r['CONTRACT_ID'], r['PLAN_ID'])
        if k not in P:
            P[k] = {'cid': k[0], 'pid': k[1], 'cn': r['CONTRACT_NAME'].strip(), 'pn': r['PLAN_NAME'].strip(),
                    'fid': r['FORMULARY_ID'].strip(), 'pr': r['PREMIUM'].strip(), 'ded': r['DEDUCTIBLE'].strip()}
            first_seg[k] = r['SEGMENT_ID']
        st = r['STATE'].strip()
        if st: states[k].add(st)
        # Stand-alone PDPs and regional PPOs are filed by region, not county: resolve the region to its states.
        if r['PDP_REGION_CODE'].strip(): states[k] |= pdp.get(r['PDP_REGION_CODE'].strip(), set())
        if r['MA_REGION_CODE'].strip():  states[k] |= ma.get(r['MA_REGION_CODE'].strip(), set())
    for k, p in P.items():
        p['st'] = ','.join(sorted(states[k]))
    return list(P.values()), first_seg

def cost(year, first_seg):
    """Initial-coverage-phase, one-month retail cost share per tier.
    Preferred-pharmacy cost share when the plan has one, otherwise standard retail."""
    C = {}
    for r in puf_rows(year, 'beneficiary_cost.txt'):
        k = (r['CONTRACT_ID'], r['PLAN_ID'])
        if first_seg.get(k) != r['SEGMENT_ID']: continue
        if r['COVERAGE_LEVEL'].strip() != '1' or r['DAYS_SUPPLY'].strip() != '1': continue
        t, a = r['COST_TYPE_PREF'].strip(), r['COST_AMT_PREF'].strip()
        if t in ('', '0'):
            t, a = r['COST_TYPE_NONPREF'].strip(), r['COST_AMT_NONPREF'].strip()
        if t in ('', '0'): continue
        try: a = ('%g' % float(a))
        except ValueError: continue
        C[f"{k[0]}|{k[1]}|{r['TIER'].strip()}"] = f'{t}|{a}'
    return C

def main():
    rx_ndc = collections.defaultdict(set)
    raw = {}
    cl_set, rx_set = set(), set()
    for y in YEARS:
        print('year', y)
        P, first_seg = plans(y)
        form = collections.OrderedDict()
        n = 0
        for r in puf_rows(y, 'basic_drugs_formulary.txt'):
            cl = '|'.join([r['TIER_LEVEL_VALUE'], r['PRIOR_AUTHORIZATION_YN'], r['STEP_THERAPY_YN'], r['QUANTITY_LIMIT_YN'],
                           r['QUANTITY_LIMIT_AMOUNT'], r['QUANTITY_LIMIT_DAYS'], r['SELECTED_DRUG_YN']])
            form.setdefault(r['FORMULARY_ID'], []).append((r['RXCUI'], cl))
            cl_set.add(cl); rx_set.add(r['RXCUI']); rx_ndc[r['RXCUI']].add(r['NDC'].strip()); n += 1
        raw[y] = {'P': P, 'form': form, 'COST': cost(y, first_seg)}
        used = {p['fid'] for p in P}
        print(f'  plans {len(P)}  formularies {len(form)} (referenced by plans: {len(used & set(form))}, plans w/o formulary: {sum(1 for p in P if p["fid"] not in form)})  rows {n}  cost keys {len(raw[y]["COST"])}')
    RX = sorted(rx_set, key=int)
    CL = sorted(cl_set)
    rxi = {r: i for i, r in enumerate(RX)}
    cli = {c: i for i, c in enumerate(CL)}
    res = {'RX': RX, 'CL': CL, 'Y': {}}
    for y in YEARS:
        C = {}
        for fid, es in raw[y]['form'].items():
            flat = []
            for r, c in es:
                flat.append(rxi[r]); flat.append(cli[c])
            C[fid] = flat
        res['Y'][y] = {'P': raw[y]['P'], 'C': C, 'COST': raw[y]['COST']}
    save('partd.json', res)
    save('rx_ndc.json', {k: sorted(v) for k, v in rx_ndc.items()})
    print('RX', len(RX), 'CL', len(CL))

if __name__ == '__main__':
    main()
