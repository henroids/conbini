"""Rebuild a raw MODE2/2352 CD image from the original raw image plus a patched 2048-byte ISO.

Only sectors whose user data changed are rewritten; their EDC/ECC are recomputed
(Mode 2 Form 1).
"""
import sys

# --- EDC (CRC32, poly 0xD8018001 reflected)
EDC = [0] * 256
for i in range(256):
    e = i
    for _ in range(8):
        e = (e >> 1) ^ (0xD8018001 if e & 1 else 0)
    EDC[i] = e

def edc(data):
    e = 0
    for b in data:
        e = EDC[(e ^ b) & 0xFF] ^ (e >> 8)
    return e

# --- ECC tables (GF(2^8))
ECC_F = [0] * 256; ECC_B = [0] * 256
for i in range(256):
    j = (i << 1) ^ (0x11D if i & 0x80 else 0)
    ECC_F[i] = j & 0xFF
    ECC_B[i ^ j & 0xFF] = i

def ecc_block(src, major_count, minor_count, major_mult, minor_inc, dest, dest_off):
    size = major_count * minor_count
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        a = b = 0
        for minor in range(minor_count):
            t = src[index]
            index += minor_inc
            if index >= size: index -= size
            a ^= t; b ^= t; a = ECC_F[a]
        a = ECC_B[ECC_F[a] ^ b]
        dest[dest_off + major] = a
        dest[dest_off + major + major_count] = a ^ b

def encode_form1(sector):
    """sector: bytearray(2352) with sync/header/subheader/data filled. Fills EDC + ECC."""
    s = sector
    e = edc(s[16:16 + 8 + 2048])
    s[2072:2076] = e.to_bytes(4, 'little')
    hdr = bytes(s[12:16])
    s[12:16] = b'\0\0\0\0'          # Mode 2: header zeroed for ECC
    buf = bytearray(s[12:12 + 2340])
    p = bytearray(172)
    ecc_block(buf, 86, 24, 2, 86, p, 0)
    buf[2064:2064 + 172] = p
    q = bytearray(104)
    ecc_block(buf, 52, 43, 86, 88, q, 0)
    s[2076:2076 + 172] = p
    s[2248:2248 + 104] = q
    s[12:16] = hdr

def bcd(x): return ((x // 10) << 4) | (x % 10)

def new_sector(lba, data2048):
    s = bytearray(2352)
    s[0:12] = b'\x00' + b'\xff' * 10 + b'\x00'
    a = lba + 150
    s[12] = bcd(a // 4500); s[13] = bcd((a // 75) % 60); s[14] = bcd(a % 75); s[15] = 2
    s[16:24] = b'\x00\x00\x08\x00\x00\x00\x08\x00'
    s[24:24 + 2048] = data2048
    encode_form1(s)
    return s

def rebuild(orig_bin, patched_iso, out_bin):
    o = open(orig_bin, 'rb'); p = open(patched_iso, 'rb'); w = open(out_bin, 'wb')
    lba = changed = 0
    while True:
        d = p.read(2048)
        if not d: break
        raw = o.read(2352)
        if raw and raw[24:24 + 2048] == d:
            w.write(raw)
        else:
            if raw:
                s = bytearray(raw); s[24:24 + 2048] = d; encode_form1(s)
            else:
                s = new_sector(lba, d)
            w.write(s); changed += 1
        lba += 1
    print('sectors', lba, 'rewritten', changed)

if __name__ == '__main__':
    rebuild(*sys.argv[1:4])
