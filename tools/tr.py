"""Translation table helper. Run from work/.

  tr.py show [START [N]]   untranslated lines: id, byte budget, Japanese
  tr.py set                merge "id<TAB>english" lines from stdin into en.tsv
  tr.py check              verify en.tsv: control codes kept, text fits, encodable

en.tsv is id<TAB>english. English is plain ASCII plus the original control codes;
Japanese characters (symbols, units such as 円) may be mixed in.
"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(__file__))
from extract import CODE

BUBBLE = re.compile(r'/k[A-Z]|/w\d{3}|/f\d\d')     # speech-bubble scripts (own parser, font 2)
ESCAPE = {'/': '／', '<': '＜', '>': '＞'}           # these bytes start engine commands
LAYOUT = {False: {'/w', '/n', '/N', '/b'},          # codes a translation may add or drop
          True: {'/r', '/n'}}

def encode(en, bubble):
    """English -> game bytes.

    Normal text: the fonts have no double quotes, so "..." becomes 「...」; every control
    code starts on an even byte and the length is even, because some engine helpers
    step through text two bytes at a time. Bubble scripts are parsed byte by byte and
    their font has a double quote, so they are written as they are."""
    out = bytearray(); pos = 0; opened = False
    for m in [*CODE.finditer(en), None]:
        for c in en[pos:m.start() if m else len(en)]:
            if c == '"' and not bubble:
                c = '」' if opened else '「'; opened = not opened
            out += ESCAPE.get(c, c).encode('cp932')
        if not bubble and len(out) % 2:
            out += b' '
        if m:
            out += m.group().encode('ascii'); pos = m.end()
    if not bubble and len(out) % 2:
        out += b' '
    return bytes(out)

def codes(s, bubble):
    """Codes that must survive translation, in order. Colour codes may move with the words."""
    keep = [c for c in CODE.findall(s) if c not in LAYOUT[bubble]]
    return [c for c in keep if not c.startswith('/c')] if bubble else sorted(keep)

def load():
    todo = json.load(open('todo.json'))
    en = {}
    for line in open('en.tsv', encoding='utf-8'):
        i, _, text = line.rstrip('\n').partition('\t')
        en[int(i)] = text
    return todo, en

def problems(todo, en):
    for t in todo:
        e = en.get(t['i'])
        if e is None:
            continue
        bubble = bool(BUBBLE.search(t['jp']))
        try:
            size = len(encode(e, bubble))
        except UnicodeEncodeError as x:
            yield t['i'], f'cannot encode: {x}', e
            continue
        if codes(e, bubble) != codes(t['jp'], bubble):
            yield t['i'], 'control codes differ from ' + t['jp'], e
        elif size > t['cap']:
            yield t['i'], f'too long ({size} > {t["cap"]} bytes)', e
        elif "'" in e:
            yield t['i'], 'apostrophe (no font has the glyph)', e

def table():
    """{japanese: english bytes} for every translated line that passes the checks."""
    todo, en = load()
    bad = {i for i, *_ in problems(todo, en)}
    return {t['jp']: encode(en[t['i']], bool(BUBBLE.search(t['jp'])))
            for t in todo if t['i'] in en and t['i'] not in bad}

if __name__ == '__main__':
    todo, en = load()
    cmd = sys.argv[1]
    if cmd == 'show':
        skip = {int(x) for x in open('skip.txt').read().split()}
        start = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        rows = [t for t in todo[start:] if t['i'] not in en and t['i'] not in skip]
        for t in rows[:int(sys.argv[3]) if len(sys.argv) > 3 else None]:
            print(t['i'], t['cap'], t['jp'], sep='\t')
    elif cmd == 'set':
        for line in sys.stdin:
            i, _, text = line.rstrip('\n').partition('\t')
            if i.strip():
                en[int(i)] = text
        with open('en.tsv', 'w', encoding='utf-8') as f:
            f.writelines(f'{i}\t{en[i]}\n' for i in sorted(en))
    elif cmd == 'check':
        bad = list(problems(todo, en))
        for b in bad:
            print(*b, sep=' | ')
        print(f'{len(en)}/{len(todo)} translated, {len(bad)} problems')
