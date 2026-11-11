"""Parse Caremark-format plan formulary PDFs and match their entries to RxCUIs (best effort)."""
import collections, re

_F = {
 'tab': 'tab tabs tablet tablets tbec tb24 tb12 tbdp tbcr t24a t12a tbpk tabpk tbdr tber tbso tb odt',
 'chew': 'chew', 'subl': 'subl', 'loz': 'lozenge lozg troc', 'film': 'film',
 'cap': 'cap caps capsule capsules cp24 cp12 cpdr cpep cpcr cpsp c12a c24a cs24 csdr cppk cptp sprk',
 'liq': 'soln sol solution susp suspension syrp syrup elix elixir conc liqd liquid emul susr sust srer',
 'pkt': 'pack packet powd powder gran',
 'inj': 'inj injection soaj sosy sopn soct solr susy supn pen auto-inj auto-injector pnij sojt sopk ajkt pskt prsy syringe vial iv',
 'kit': 'kit',
 'top': 'crea cream oint ointment gel lotn lotion foam sham shampoo soap pste paste swab pads tinc aers',
 'patch': 'pt24 pt72 ptwk pttw patch td',
 'supp': 'supp suppository enem enema',
 'inh': 'aero aerosol aepb aerb aerp nebu inhaler inhal neb hfa',
 'drop': 'drops gtts ophth otic dro', 'nasal': 'nasal spray spr', 'ins': 'insr ring iud implant impl',
}
for _k, _v in (('chew', 'chw'), ('liq', 'sus syr'), ('pkt', 'pow'), ('kit', 'pak'), ('top', 'cre oin lot'), ('inh', 'aer'), ('supp', 'sup')):
    _F[_k] += ' ' + _v
_F['misc'] = 'mis'
FORM_TOKENS = {t: k for k, v in _F.items() for t in v.split()}
ER_TOKENS = set('tb24 tb12 tbcr t24a t12a tber cp24 cp12 cpcr cpep c12a c24a cs24 er xr sr cr la xl 24hr 12hr extended srer susr'.split())
DR_TOKENS = set('tbec tbdr cpdr csdr dr ec delayed'.split())
SALTS = set('''hcl hydrochloride dihydrochloride sodium potassium calcium magnesium sulfate bisulfate tartrate bitartrate maleate acetate
 succinate besylate mesylate fumarate phosphate citrate bromide hydrobromide chloride nitrate oxalate tosylate valerate propionate
 dipropionate furoate benzoate pamoate hyclate monohydrate dihydrate trihydrate anhydrous disodium dipotassium hbr mononitrate dinitrate
 lactate gluconate carbonate bicarbonate stearate palmitate decanoate enanthate cypionate medoxomil axetil proxetil pivoxil etexilate
 cilexetil marboxil trometamol tromethamine meglumine lysine arginine diolamine olamine glycolate butyrate aceponate
 hemifumarate hemihydrate sesquihydrate xinafoate napsylate edisylate esylate saccharate dimesylate monohydrochloride
 er xr sr cr dr ec la xl odt hfa oral topical ophthalmic otic nasal for the of in extended release delayed micronized
 base equivalent equiv eq human recombinant k acetonide hexacetonide diacetate pivalate dipivoxil sulf sl im iv sq subcutaneous pf
 vaginal rectal inhalation chewable microsize ultramicrosize beads particles ir conc w d5w ns intrathecal intravenous injection
 hydrobromide-hydrate glargine-yfgn'''.split()) - {'glargine-yfgn'}
RX_FORM = [('TABLET', 'tab'), ('CAPSULE', 'cap'), ('ORAL SOLUTION', 'liq'), ('SUSPENSION', 'liq'), ('ORAL LIQUID', 'liq'), ('SYRUP', 'liq'),
           ('ELIXIR', 'liq'), ('INJECT', 'inj'), ('SYRINGE', 'inj'), ('PEN INJECTOR', 'inj'), ('AUTO-INJECTOR', 'inj'), ('CARTRIDGE', 'inj'),
           ('CREAM', 'top'), ('OINTMENT', 'top'), ('GEL', 'top'), ('LOTION', 'top'), ('FOAM', 'top'), ('SHAMPOO', 'top'),
           ('TRANSDERMAL', 'patch'), ('PATCH', 'patch'), ('SUPPOSITORY', 'supp'), ('ENEMA', 'supp'), ('INHAL', 'inh'), ('NEBUL', 'inh'),
           ('OPHTHALMIC', 'drop'), ('OTIC', 'drop'), ('NASAL', 'nasal'), ('GRANULE', 'pkt'), ('POWDER', 'pkt'), ('CHEWABLE', 'chew'),
           ('SUBLINGUAL', 'subl'), ('LOZENGE', 'loz'), ('FILM', 'film'), ('IMPLANT', 'ins'), ('RING', 'ins'), ('KIT', 'kit'), ('PACK', 'kit')]

def norm_tokens(name):
    """Ingredient text -> frozenset of ingredient keys (salts and release descriptors removed)."""
    s = re.sub(r'\([^)]*\)', ' ', name.lower())
    s = re.sub(r'\s+w/\s+|\s*&\s*|\s+and\s+|\s*/\s*|\s*,\s*|\s+-\s+', ' | ', s)
    s = re.sub(r'(?<=[a-z])-(?=[a-z])', ' | ', s)
    s = re.sub(r'\btenofovir df\b', 'tenofovir disoproxil', s)
    parts = []
    for p in s.split('|'):
        toks = [t for t in re.findall(r'[a-z][a-z0-9\-]*', p) if t not in SALTS]
        if toks: parts.append(' '.join(toks))
    return frozenset(parts)

def nums(s):
    if not s: return set()
    return {('0' + n if n.startswith('.') else n).rstrip('0').rstrip('.') if '.' in n else n for n in re.findall(r'\d+(?:\.\d+)?|\.\d+', s.replace(',', ' '))}

def split_entry(name):
    """Caremark-style 'drug form strengths' -> (ingredient/brand text, rest)."""
    if '  ' in name.strip():
        a, b = name.strip().split('  ', 1)
        return a.strip(), b.strip()
    toks = name.split()
    for i, t in enumerate(toks):
        tl = t.lower().strip('(),;')
        if i > 0 and (tl in FORM_TOKENS or re.match(r'^[\d.]', tl)):
            return ' '.join(toks[:i]), ' '.join(toks[i:])
    return name.strip(), ''

def classify(rest):
    toks = [t.lower().strip('(),;') for t in rest.split()]
    return {FORM_TOKENS[t] for t in toks if t in FORM_TOKENS}, bool(set(toks) & ER_TOKENS), bool(set(toks) & DR_TOKENS)

def rx_class(f):
    f = f.upper(); c = {v for k, v in RX_FORM if k in f}
    if 'TOPICAL' in f: c = {'top'} | (c - {'liq'})
    return c, ('EXTENDED' in f or ' 12 HR' in f or ' 24 HR' in f), ('DELAYED' in f)

def parse_formulary(path):
    """Positional parse of a Caremark-format formulary PDF -> ([{name, tier, req}], 'effective' text).
    Columns are fixed: category headings x~85, drug names x~100, tier x~373, requirements x~410."""
    import pymupdf
    doc = pymupdf.open(path); entries, eff = [], ''
    for pg in doc:
        lines = []
        for b in pg.get_text('dict')['blocks']:
            for l in b.get('lines', []):
                t = ''.join(s['text'] for s in l['spans']).strip()
                if t: lines.append((l['bbox'][1], l['bbox'][0], t))
        if not eff:
            for _, _, t in lines:
                m = re.search(r'(updated on \d+/\d+/\d{4}|up to date as of \w+ \d{4}|Effective \d+/\d+/\d{4})', t, re.I)
                if m: eff = m.group(1); break
        if not any(t == 'Drug Tier' for _, _, t in lines): continue
        hy = min(y for y, x, t in lines if t == 'Drug Tier')
        body = sorted((y, x, t) for y, x, t in lines if hy + 4 < y < 712)
        tiers = [(y, t) for y, x, t in body if 340 < x < 400 and re.match(r'^\d$', t)]
        for i, (ty, tier) in enumerate(tiers):
            ny = tiers[i + 1][0] if i + 1 < len(tiers) else 9999
            name = ' '.join(t for y, x, t in body if 95 < x < 340 and ty - 2 <= y < ny - 2)
            req = ' '.join(t for y, x, t in body if x >= 400 and ty - 2 <= y < ny - 2)
            if name: entries.append({'name': re.sub(r'[ \t]{2,}', '  ', name).strip(), 'tier': tier, 'req': req})
    return entries, eff

def flags(req):
    f = ''
    if re.search(r'\bPA\b(?!\*\*)', req): f += 'P'
    if re.search(r'PA\*\*', req): f += 'p'            # PA only if step therapy is not met
    if re.search(r'\bST\b', req): f += 'S'
    if re.search(r'\bQL\b', req): f += 'Q'
    if re.search(r'\b(SGM|ONC)\b', req): f += 'M'
    if re.search(r'\bOTC\b', req): f += 'O'
    return f

def match(entries, D, trace=None):
    """-> ({RxCUI: 'tier|flags[~]'}, {BRAND: 'tier|flags'}, stats).  '~' marks a match where form or strength was not confirmed."""
    brand, generic = collections.defaultdict(list), collections.defaultdict(list)
    for e in entries:
        nm, rest = split_entry(e['name'])
        e['cls'], e['er'], e['dr'] = classify(rest); e['nums'] = nums(rest); e['nm'] = nm
        letters = re.sub(r'[^A-Za-z]', '', nm)
        if letters and letters.upper() == letters:
            brand[re.sub(r'[^A-Z0-9]', '', nm.upper())].append(e)
            first = re.sub(r'[^A-Z0-9]', '', nm.upper().split()[0])
            if len(first) > 3: brand['~' + first].append(e)
        else:
            generic[norm_tokens(nm)].append(e)
    def pick(cands, d):
        cls, er, dr = rx_class(d['f']); n = nums(d['s'])
        best, bs = None, -99
        for e in cands:
            s = 0
            if cls and e['cls'] and (cls & e['cls']): s += 4
            elif cls and e['cls']: s -= 2
            if er == e['er']: s += 1
            if dr == e['dr']: s += 1
            if n and e['nums'] and (n & e['nums']): s += 3
            if s > bs or (s == bs and int(e['tier']) < int(best['tier'])): best, bs = e, s
        return best, bs
    out_rx, stats = {}, collections.Counter()
    for rx, d in D.items():
        if d['b']:
            k = re.sub(r'[^A-Z0-9]', '', d['b']); kind = 'brand'
            cands = brand.get(k) or brand.get('~' + re.sub(r'[^A-Z0-9]', '', d['b'].split()[0])) or []
        else:
            ing = d.get('g') or ' / '.join(re.sub(r'\s+[\d.].*$', '', x.strip()) for x in d['s'].split(' / ')) or re.sub(r'\s+[\d.].*$', '', d['d'])
            cands = generic.get(norm_tokens(ing), []); kind = 'generic'
            if not cands:                                             # unbranded biologics are printed in capitals
                cands = brand.get(re.sub(r'[^A-Z0-9]', '', ing.upper().replace('/', ''))) or []
        if not cands:
            stats[kind + ' not listed'] += 1; continue
        e, s = pick(cands, d)
        cls = rx_class(d['f'])[0]
        if cls and e['cls'] and not (cls & e['cls']):
            stats[kind + ' other form only'] += 1; continue        # e.g. tablet listed, injection asked
        val = e['tier'] + '|' + flags(e['req'])
        if s < 9: val += '~'                                         # exact only when form, release type and strength all agree
        out_rx[rx] = val; stats[kind + (' exact' if s >= 9 else ' approx')] += 1
        if trace is not None: trace[rx] = e['name']
    bn = {}
    for k, es in brand.items():
        if k.startswith('~'): continue
        e = min(es, key=lambda x: int(x['tier']))
        bn[es[0]['nm'].upper()] = e['tier'] + '|' + flags(e['req'])
    return out_rx, bn, stats
