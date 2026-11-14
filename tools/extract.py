"""Find the game's Shift-JIS text and merge it into work/lines.json + work/todo.json.

lines.json  one entry per occurrence: file, off, len (bytes), pad (NULs after), jp
todo.json   one entry per unique string: i (stable id), jp, cap (bytes that fit every copy)

The merge only ever adds, so ids stay valid for en.tsv. Run from work/:
    python3 -I ../scripts/extract.py
Sources: the main program's data, and the decompressed CN3.PAC entries. Entries 23 and
26 are databases whose name fields follow binary data, so there a string may start
anywhere, not just after a NUL.
"""
import glob, json, re

ELF = 'files/SLPM_623.22'
ELF_DATA = 0x300000                     # text strings live above this file offset
ELF_MANUAL = (0x422150, 0x423668)       # strings that directly follow binary data
EMBEDDED = ('pac/CN3/0023.bin.dec', 'pac/CN3/0026.bin.dec')

# control codes: bubble scripts (/m(..)(..) /w045 /s00 /f05 /i10 /c2 /g1 /p /kB) and
# normal text (/n /N /r /w /b /k /I100 /s0 /d4 /0../9, printf formats)
CODE = re.compile(r'/m\([^)]*\)\([^)]*\)|/w\d{3}|/[sfi]\d\d|/[cgsd]\d|/I\d+|/k[A-Z]?|/[nNrwbp]|/\d'
                  r'|%[-0-9.]*[sdxcu]|%%')
JP = "\u00d7\u3000-\u30ff\u4e00-\u9fff\uff01-\uff5e\u2010-\u266f"   # kana, kanji, full-width, symbols
TEXT = re.compile(f'[{JP} ]+')
WORD = re.compile('[ぁ-ヺ一-鿿]')
RUN = re.compile(rb'(?:[\x81-\x84\x88-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]|/[nwNb]|%[sd])+(?=\x00)')

def is_text(s):
    body = CODE.sub('', s)
    return len(WORD.findall(body)) >= 2 and TEXT.fullmatch(body) is not None

def hit(data, start):
    end = data.find(b'\0', start)
    if end < 0:
        return None
    pad = 0
    while end + pad < len(data) and data[end + pad] == 0:
        pad += 1
    try:
        return {'off': start, 'len': end - start, 'pad': pad, 'jp': data[start:end].decode('cp932')}
    except UnicodeDecodeError:
        return None

def scan(data, lo=0, embedded=False):
    """Strings that start after a NUL; with `embedded`, also runs of pure text ending in a NUL."""
    starts = {i + 1 for i in range(max(lo, 1) - 1, len(data) - 1) if data[i] == 0 and data[i + 1]}
    if embedded:
        starts |= {m.start() for m in RUN.finditer(data, lo)}
    for s in sorted(starts):
        h = hit(data, s)
        if h and is_text(h['jp']):
            yield h

def main():
    lines = json.load(open('lines.json'))
    todo = json.load(open('todo.json'))
    covered = {}
    for x in lines:
        covered.setdefault(x['file'], set()).update(range(x['off'], x['off'] + x['len']))
    found = []
    elf = open(ELF, 'rb').read()
    found += [dict(h, file=ELF) for h in scan(elf, ELF_DATA)]
    found += [dict(hit(elf, o), file=ELF) for o in ELF_MANUAL]
    for f in sorted(glob.glob('pac/CN3/*.dec')):
        found += [dict(h, file=f) for h in scan(open(f, 'rb').read(), embedded=f in EMBEDDED)]

    by_jp = {t['jp']: t for t in todo}
    added = 0
    for h in found:
        if h['off'] in covered.get(h['file'], ()):
            continue
        covered.setdefault(h['file'], set()).update(range(h['off'], h['off'] + h['len']))
        lines.append(h); added += 1
        cap = h['len'] + h['pad'] - 1
        t = by_jp.get(h['jp'])
        if t is None:
            t = by_jp[h['jp']] = {'i': len(todo), 'jp': h['jp'], 'cap': cap}
            todo.append(t)
            print(t['i'], cap, h['file'], hex(h['off']), h['jp'][:60], sep='\t')
        t['cap'] = min(t['cap'], cap)
    json.dump(lines, open('lines.json', 'w'), ensure_ascii=False)
    json.dump(todo, open('todo.json', 'w'), ensure_ascii=False)
    print(f'{added} occurrences added; {len(lines)} lines, {len(todo)} unique')

if __name__ == '__main__':
    main()
