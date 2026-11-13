"""Stage 5 - assemble the page.

Inputs  : out/partd.json, out/drugs.json, out/medical.json, out/plans.json, sources/build_meta.json,
          sources/hcpcs_biosimilar_codes.csv (see biosimilars.py), build/page/*
Outputs : ../index.html                 single self-contained file (open it directly in a browser)
          out/artifact_page.html        same page without the document skeleton, for publishing as a claude.ai artifact
Data is embedded as gzip + base64 blobs and unpacked in the browser with DecompressionStream; the year blobs load on demand.
"""
import gzip, base64, datetime
from common import *
from biosimilars import load_hcpcs, enrich, print_report

def hcpcs_source(meta):
    return ['Biosimilars: HCPCS code, biosimilar name, molecule and code dates', 'CMS HCPCS Level II code descriptors, biosimilar range Q5098 and up', meta['hcpcs_asof']]

def build_date():
    return os.environ.get('LOOKUP_BUILD_DATE') or datetime.date.today().strftime('%B %-d, %Y')

def blob(obj):
    raw = json.dumps(obj, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    return base64.b64encode(gzip.compress(raw, 9, mtime=0)).decode('ascii'), len(raw)   # mtime=0 keeps rebuilds byte-identical

def main():
    partd, drugs, med, plans = load('partd.json'), load('drugs.json'), load('medical.json'), load('plans.json')
    meta = json.load(open(src('build_meta.json')))
    prev = json.load(open(src('carry_forward.json')))
    F = plans['FORM']
    assert F['mpq']['rx'] == F['mpe']['rx'], 'MetroPlus QHP and EP lists differ: carry both'
    FORM = {
        'hf26': {'rx': F['hf26']['rx'], 'bn': F['hf26']['bn'], 'label': 'Healthfirst Leaf, Leaf Premier and Essential Plan comprehensive drug list', 'eff': meta['hf_form']['hf26'], 'short': 'Leaf / EP'},
        'hf27': {'rx': F['hf27']['rx'], 'bn': F['hf27']['bn'], 'label': 'Healthfirst Leaf, Leaf Premier and Essential Plan comprehensive drug list', 'eff': meta['hf_form']['hf27'], 'short': 'Leaf / EP'},
        'mp':   {'rx': F['mpq']['rx'],  'bn': F['mpq']['bn'],  'label': 'MetroPlus Marketplace, Gold, GoldCare and Essential Plan formulary', 'eff': meta['mp_form_note'], 'short': 'Marketplace / EP'},
    }
    states = sorted({s for y in YEARS for p in partd['Y'][y]['P'] for s in p['st'].split(',') if s})
    mm = med['meta']
    sources = [
        ['Medicare Part D 2026: plans, formularies, tiers, PA / ST / QL, cost share', 'CMS Quarterly Prescription Drug Plan Formulary, Pharmacy Network, and Pricing Information (' + meta['years']['2026']['file'] + ')', meta['years']['2026']['asof']],
        ['Medicare Part D 2027: plans, formularies, tiers, PA / ST / QL, cost share', 'CMS Monthly Prescription Drug Plan Formulary and Pharmacy Network Information (' + meta['years']['2027']['file'] + ')', meta['years']['2027']['asof']],
        ['Drug names, strengths and dose forms', 'CMS Formulary Reference Files', meta['frf']],
        ['Dollar estimates for coinsurance', 'CMS quarterly pricing file: median 30-day unit cost across all plans', 'Q3 2026'],
        ['Medicare Part B payment limits and drugs not payable', 'CMS Medicare Part B Payment Limit File; Drugs Not Payable Under Part B', mm['partb_eff']],
        ['HCPCS code for a Part D drug', 'CMS ASP, AWP, OPPS and PrEP NDC-HCPCS crosswalks; NYS PAD list', meta['crosswalk']],
        hcpcs_source(meta),
        ['NY Medicaid pharmacy benefit (NYRx): preferred, non-preferred, covered, PA', 'eMedNY List of Medicaid Reimbursable Drugs', meta['nyrx_date']],
        ['NY Medicaid medical benefit: covered codes, PA, manual review', 'NYS DOH List of Physician Administered Drugs', 'effective ' + mm['pad_eff']],
        ['NY Medicaid medical benefit: fallback code list', 'eMedNY Physician Manual Fee Schedule, Section 3 (Drugs)', 'effective ' + mm['nysfs_eff']],
        ['Healthfirst Leaf / Essential Plan pharmacy formulary', 'Healthfirst Comprehensive Drug List (NYSOH)', meta['hf_form']['hf26'] + ' for 2026; ' + meta['hf_form']['hf27'] + ' for 2027'],
        ['MetroPlus Marketplace / Gold / GoldCare / Essential Plan pharmacy formulary', 'MetroPlusHealth formulary', meta['mp_form_note']],
        ['Healthfirst medical benefit: PA and preferred products', 'Medications Requiring Prior Authorization Under the Medical Benefit', 'revised ' + plans['meta']['hf_grid_rev']],
        ['MetroPlus medical benefit: PA by line of business', 'Physician Administered Drugs Requiring Prior Authorization (Medicare; Medicaid/HARP; QHP/EP/CHP/Gold)', 'updated ' + plans['meta']['mp_grid_upd']],
    ]
    META = {'years': {y: {'label': meta['years'][y]['label']} for y in YEARS}, 'default_year': meta['default_year'], 'example': meta['example'],
            'price_label': meta['price_label'], 'nyrx_date': meta['nyrx_date'], 'partb_eff': mm['partb_eff'], 'pad_eff': mm['pad_eff'], 'nysfs_eff': mm['nysfs_eff'],
            'hf_grid_rev': plans['meta']['hf_grid_rev'], 'mp_grid_upd': plans['meta']['mp_grid_upd'], 'sources': sources,
            'built': build_date()}
    common = {'D': drugs['D'], 'RX': partd['RX'], 'CL': partd['CL'], 'STATES': states, 'DP': drugs['DP'], 'NYMC': drugs['NYMC'], 'NYPA': drugs['NYPA'],
              'PAYB': med['PAYB'], 'NOTPAYB': med['NOTPAYB'], 'PBD': med['PBD'], 'BIOSIM': med['BIOSIM'], 'NYSMED': med['NYSMED'], 'PADN': med['PADN'], 'NYSFS': med['NYSFS'],
              'HFPA': {c: {k: v for k, v in e.items() if k != 'l'} for c, e in plans['HFPA'].items()}, 'MPPA': plans['MPPA'], 'OVR': prev.get('OVR', {}), 'FORM': FORM, 'META': META}
    write_page(common, {y: partd['Y'][y] for y in YEARS})

def write_page(common, years):
    print_report(enrich(common, load_hcpcs()))
    blobs = {'common': blob(common)}
    for y in YEARS: blobs[y] = blob(years[y])
    for k, (b, n) in blobs.items(): print(f'  blob {k}: {n/1e6:.1f} MB json -> {len(b)/1e6:.2f} MB embedded')

    page = os.path.join(HERE, 'page')
    rd = lambda f: open(os.path.join(page, f), encoding='utf-8').read()
    js = ''.join(rd(f'app{i}.js') for i in range(1, 8))
    data = ''.join(f'<script type="application/octet-stream" id="z-{k}">{b}</script>\n' for k, (b, n) in blobs.items())
    font = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap">\n'
    core = font + '<style>\n' + rd('style.css') + '</style>\n' + rd('body.html') + data + '<script>\n' + js + '</script>\n'
    title = '<title>Drug Coverage Lookup</title>\n'
    art = title + '<meta name="claude:viewport-fit-sides" content="cover">\n' + core
    full = '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n<meta name="viewport" content="width=device-width, initial-scale=1.0">\n' + title + '</head>\n<body>\n' + core + '</body>\n</html>\n'
    with open(os.path.join(HERE, '..', 'index.html'), 'w', encoding='utf-8') as f: f.write(full)
    with open(out('artifact_page.html'), 'w', encoding='utf-8') as f: f.write(art)
    print(f'index.html {len(full)/1e6:.2f} MB | artifact page {len(art)/1e6:.2f} MB')

if __name__ == '__main__':
    main()
