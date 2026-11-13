"""Filter raw hits into a clean line list (drops binary noise)."""
import json, re, sys

CODE = re.compile(r'/n|/r|/k[A-Z]?|/I\d+|%[0-9]*[sdx]|%%')

def is_noise(s):
    core = CODE.sub('', s)
    asc = [c for c in core if ord(c) < 0x80 and c not in ' ']
    if asc:
        return True                      # stray ASCII inside a JP string = noise
    jp = [c for c in core if c not in ' 　']
    if len(jp) < 2:
        return True
    # kanji-only 2-char strings next to binary are usually noise unless common
    return False

def main(src, dst):
    h = json.load(open(src))
    out = []
    for f, L in h.items():
        for x in L:
            if not is_noise(x['jp']):
                x['file'] = f
                out.append(x)
    json.dump(out, open(dst, 'w'), ensure_ascii=False)
    print(len(out), 'lines;', len({x['jp'] for x in out}), 'unique', file=sys.stderr)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
