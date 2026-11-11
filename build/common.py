"""Shared paths and helpers for the Drug Coverage Lookup build."""
import os, io, csv, json, zipfile, re

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.environ.get('LOOKUP_SRC', os.path.join(HERE, '..', 'sources'))
OUT = os.environ.get('LOOKUP_OUT', os.path.join(HERE, 'out'))
os.makedirs(OUT, exist_ok=True)

YEARS = ['2026', '2027']

def src(name):
    return os.path.join(SRC, name)

def out(name):
    return os.path.join(OUT, name)

def save(name, obj):
    with open(out(name), 'w') as f:
        json.dump(obj, f, separators=(',', ':'), ensure_ascii=False)

def load(name):
    with open(out(name)) as f:
        return json.load(f)

def puf_rows(year, member):
    """Yield dict rows from a pipe-delimited CMS PUF text file inside partd_<year>.zip."""
    with zipfile.ZipFile(src(f'partd_{year}.zip')) as z:
        with z.open(member) as raw:
            txt = io.TextIOWrapper(raw, encoding='latin-1', newline='')
            rd = csv.reader(txt, delimiter='|')
            hdr = [h.strip() for h in next(rd)]
            for row in rd:
                yield dict(zip(hdr, row))

def ndc11(s):
    """Normalise an NDC written 5-4-2 with hyphens (or already 11 digits) to 11 digits."""
    s = (s or '').strip()
    if '-' in s:
        a = s.split('-')
        if len(a) == 3:
            return a[0].zfill(5) + a[1].zfill(4) + a[2].zfill(2)
    d = re.sub(r'\D', '', s)
    return d.zfill(11) if d else ''

STATE_ABBR = {
 'Alabama':'AL','Alaska':'AK','Arizona':'AZ','Arkansas':'AR','California':'CA','Colorado':'CO','Connecticut':'CT',
 'Delaware':'DE','District of Columbia':'DC','Washington D.C.':'DC','Florida':'FL','Georgia':'GA','Hawaii':'HI','Idaho':'ID','Illinois':'IL',
 'Indiana':'IN','Iowa':'IA','Kansas':'KS','Kentucky':'KY','Louisiana':'LA','Maine':'ME','Maryland':'MD',
 'Massachusetts':'MA','Michigan':'MI','Minnesota':'MN','Mississippi':'MS','Missouri':'MO','Montana':'MT',
 'Nebraska':'NE','Nevada':'NV','New Hampshire':'NH','New Jersey':'NJ','New Mexico':'NM','New York':'NY',
 'North Carolina':'NC','North Dakota':'ND','Ohio':'OH','Oklahoma':'OK','Oregon':'OR','Pennsylvania':'PA',
 'Puerto Rico':'PR','Rhode Island':'RI','South Carolina':'SC','South Dakota':'SD','Tennessee':'TN','Texas':'TX',
 'Utah':'UT','Vermont':'VT','Virginia':'VA','Washington':'WA','West Virginia':'WV','Wisconsin':'WI','Wyoming':'WY',
 'American Samoa':'AS','Guam':'GU','Northern Mariana Islands':'MP','Virgin Islands':'VI','U.S. Virgin Islands':'VI',
}
