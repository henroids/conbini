import sys, re

# Find runs of Shift-JIS double-byte text (hiragana/katakana/kanji/fullwidth) in a binary.
def is_lead(b): return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF

def scan(data, minchars=4):
    i, n = 0, len(data)
    out = []
    while i < n - 1:
        start = i; cnt = 0; j = i
        while j < n - 1:
            b = data[j]
            if is_lead(b) and 0x40 <= data[j+1] <= 0xFC and data[j+1] != 0x7F:
                j += 2; cnt += 1
            elif 0x20 <= b < 0x7F and cnt > 0:
                j += 1
            else:
                break
        if cnt >= minchars:
            try:
                s = data[start:j].decode('cp932')
                out.append((start, s))
            except UnicodeDecodeError:
                pass
            i = j
        else:
            i += 1
    return out

if __name__ == '__main__':
    path = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    data = open(path, 'rb').read()
    res = scan(data)
    print(f'# {path}: {len(res)} strings')
    for off, s in res[:limit]:
        print(hex(off), s)
