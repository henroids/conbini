"""Translation helper.
  tr.py show START COUNT      -> print untranslated lines with their wide-letter budget
  tr.py check                 -> verify en.tsv: fits budget, keeps control codes, encodes
  tr.py export OUT.tsv        -> write jp<TAB>FW:en table for build.py
en.tsv format: id<TAB>english   (plain ASCII; converted to full-width at build time)
"""
import sys, json, csv, re, os
sys.path.insert(0, os.path.dirname(__file__))
from build import fullwidth, CODE, ascii_encode

W = '/home/claude/conbini/work/'
todo = json.load(open(W + 'todo.json'))

def load_en(name='en.tsv'):
    en = {}
    if os.path.exists(W + name):
        for row in csv.reader(open(W + name, encoding='utf-8'), delimiter='\t', quoting=csv.QUOTE_NONE):
            if len(row) >= 2 and row[0].isdigit():
                en[int(row[0])] = row[1]
    return en

def body_len(s):
    return len(CODE.sub('', s))

def check(en):
    bad = []
    for t in todo:
        i = t['i']
        if i not in en: continue
        e = en[i]
        skip = ('/w', '/n', '/N')
        if sorted(c for c in CODE.findall(e) if c not in skip) != sorted(c for c in CODE.findall(t['jp']) if c not in skip):
            bad.append((i, 'codes differ', t['jp'], e))
        elif len(ascii_encode(e)) > t['cap']:
            bad.append((i, f'too long {len(ascii_encode(e))}>{t["cap"]} bytes', t['jp'], e))
        else:
            try:
                ascii_encode(e)
            except UnicodeEncodeError as x:
                bad.append((i, 'unencodable ' + str(x), t['jp'], e))
    return bad

if __name__ == '__main__':
    cmd = sys.argv[1]
    en = load_en()
    if cmd == 'show':
        s, n = int(sys.argv[2]), int(sys.argv[3])
        for t in todo[s:s + n]:
            if t['i'] not in en:
                print(f"{t['i']}\t{t['cap']}\t{t['jp']}")
    elif cmd == 'check':
        bad = check(en)
        for b in bad: print(*b, sep=' | ')
        print(f'{len(en)}/{len(todo)} translated, {len(bad)} problems')
    elif cmd == 'export':
        w = csv.writer(open(sys.argv[2], 'w', encoding='utf-8'), delimiter='\t', lineterminator='\n', quoting=csv.QUOTE_NONE, escapechar='\\')
        bad = {b[0] for b in check(en)}
        for t in todo:
            i = t['i']
            if i in en and i not in bad:
                w.writerow([t['jp'], 'AS:' + en[i]])
