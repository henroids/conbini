"""Extract null-terminated Shift-JIS strings from the game's text files.

Each hit records file, offset, original byte length and the decoded text.
A string counts when it sits between NUL bytes (or a record boundary),
decodes cleanly as cp932 and contains at least one full-width character.
"""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(__file__))

ALLOWED_ASCII = set(range(0x20, 0x7F))

def valid_sjis_segment(seg):
    i, wide = 0, 0
    while i < len(seg):
        b = seg[i]
        if (0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF) and i + 1 < len(seg):
            t = seg[i + 1]
            if not (0x40 <= t <= 0xFC and t != 0x7F):
                return False
            # reject rare/user-defined rows that show up in binary noise
            if b >= 0xEB:
                return False
            wide += 1; i += 2
        elif b in ALLOWED_ASCII:
            i += 1
        else:
            return False
    return wide >= 1

def looks_like_text(s):
    # require some kana/kanji/fullwidth punctuation, and not mostly box-drawing noise
    jp = sum(1 for c in s if '぀' <= c <= 'ヿ' or '一' <= c <= '鿿' or '！' <= c <= '～' or c in '、。「」『』・ー…！？（）')
    return jp >= max(1, len(s.replace('/n', '')) * 0.5)

def extract(data):
    hits = []
    i, n = 0, len(data)
    while i < n:
        if data[i] == 0:
            i += 1; continue
        j = data.find(b'\0', i)
        if j < 0: j = n
        seg = data[i:j]
        # string must start right after a NUL (or file start)
        if (i == 0 or data[i - 1] == 0) and valid_sjis_segment(seg):
            try:
                s = seg.decode('cp932')
            except UnicodeDecodeError:
                s = ''
            if s and looks_like_text(s):
                # count trailing NUL padding as potential extra room
                k = j
                while k < n and data[k] == 0: k += 1
                hits.append({'off': i, 'len': len(seg), 'pad': k - j, 'jp': s})
        i = j + 1
    return hits

if __name__ == '__main__':
    out = {}
    for p in sys.argv[1:]:
        out[p] = extract(open(p, 'rb').read())
        print(p, len(out[p]), file=sys.stderr)
    json.dump(out, sys.stdout, ensure_ascii=False)
