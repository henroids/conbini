"""LZSS compressor matching the game's LZS format (see lzs.py)."""
import struct

N, F, THRESH = 4096, 18, 2

def compress(data):
    """Optimal parse (shortest bit cost) over all matches in the window."""
    n = len(data)
    # candidate matches per position: best (len,pos) for each length via longest match search
    chains = {}
    best = [None] * n
    for i in range(n):
        if i + 2 < n:
            key = data[i:i + 3]
            cands = chains.get(key)
            bl, bp = 0, 0
            if cands:
                lo = i - (N - F)
                mx = min(F, n - i)
                for q in reversed(cands):
                    if q < lo:
                        break
                    L = 3
                    while L < mx and data[q + L] == data[i + L]:
                        L += 1
                    if L > bl:
                        bl, bp = L, q
                        if L == mx:
                            break
                # trim old entries occasionally
                if len(cands) > 4096 and cands[0] < lo:
                    k = 0
                    while cands[k] < lo: k += 1
                    del cands[:k]
            if bl >= 3:
                best[i] = (bl, bp)
            chains.setdefault(key, []).append(i)
    # cost in bits: literal 9, match 17; dp from the end
    cost = [0] * (n + 1)
    choice = [0] * n
    for i in range(n - 1, -1, -1):
        c = cost[i + 1] + 9; ch = 1
        if best[i]:
            bl = best[i][0]
            for L in range(3, bl + 1):
                v = cost[i + L] + 17
                if v < c:
                    c, ch = v, L
        cost[i] = c; choice[i] = ch
    return _emit(data, best, choice)

def _emit(data, best, choice):
    n = len(data)
    out = bytearray(b'LZS\0' + struct.pack('<I', n))
    i = 0
    while i < n:
        flag_pos = len(out); out.append(0); flags = 0
        for bit in range(8):
            if i >= n:
                break
            L = choice[i]
            if L >= 3:
                best_len, best_pos = L, best[i][1]
            else:
                best_len = 0
            if best_len > THRESH:
                ring = (0xFEE + best_pos) & 0xFFF
                out.append(ring & 0xFF)
                out.append(((ring >> 4) & 0xF0) | (best_len - 3))
                step = best_len
            else:
                flags |= 1 << bit
                out.append(data[i])
                step = 1
            i += step
        out[flag_pos] = flags
    return bytes(out)

if __name__ == '__main__':
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    import lzs
    raw = open(sys.argv[1], 'rb').read()
    orig = lzs.decompress(raw) if raw[:4] == b'LZS\0' else raw
    c = compress(orig)
    assert lzs.decompress(c) == orig, 'roundtrip failed'
    print('ok', len(orig), '->', len(c), '(original', len(raw), ')')
