"""Build a translated ISO from the original ISO plus a translation table.

translations.tsv columns: jp<TAB>en  (jp uses /n etc. exactly as in the game)
Prefix en with "FW:" to encode it as full-width Shift-JIS (fallback test).
"""
import sys, os, struct, json, shutil, csv
sys.path.insert(0, os.path.dirname(__file__))
import pycdlib, lzs, lzs_comp, pac as pacmod, asciipatch

SECTOR = 2048

import re
CODE = re.compile(r'/n|/r|/w|/k[A-Z]?|/I\d+|%[0-9]*[sdx]')

def fullwidth(s):
    """Convert ASCII to full-width Shift-JIS-able chars, leaving control codes untouched."""
    out = []; pos = 0
    for m in list(CODE.finditer(s)) + [None]:
        end = m.start() if m else len(s)
        for c in s[pos:end]:
            if c == ' ': out.append('　')
            elif c == '-': out.append('ー' if False else '－')
            elif c == "'": out.append('’')
            elif c == '"': out.append('”')
            elif c == '~': out.append('～')
            elif '!' <= c <= '~': out.append(chr(ord(c) + 0xFEE0))
            else: out.append(c)
        if m: out.append(m.group()); pos = m.end()
    return ''.join(out)

ESCAPE = {'/': '／', '<': '＜', '>': '＞'}   # these bytes are engine commands

def ascii_encode(s):
    """Plain-letter mode (needs asciipatch). Control codes stay as-is; '/', '<', '>' in
    prose become full-width; every control code starts on an even byte and the whole
    string has even length, because some engine helpers walk text 2 bytes at a time."""
    out = bytearray(); pos = 0; quote_open = False
    for m in list(CODE.finditer(s)) + [None]:
        end = m.start() if m else len(s)
        seg = ''
        for c in s[pos:end]:
            if c == '"':                      # font has no curly quotes: use 「 」
                seg += '\u300d' if quote_open else '\u300c'; quote_open = not quote_open
            else:
                seg += ESCAPE.get(c, c)
        out += seg.encode('cp932')
        if len(out) % 2:
            out += b' '
        if m:
            out += m.group().encode('ascii'); pos = m.end()
    if len(out) % 2:
        out += b' '
    return bytes(out)

def encode(en):
    if en.startswith('FW:'):
        return fullwidth(en[3:]).encode('cp932')
    if en.startswith('AS:'):
        return ascii_encode(en[3:])
    return en.encode('cp932')

def load_tr(path):
    tr = {}
    with open(path, encoding='utf-8') as f:
        for row in csv.reader(f, delimiter='\t'):
            if len(row) >= 2 and row[1].strip() and not row[0].startswith('#'):
                tr[row[0]] = row[1]
    return tr

def apply(buf, lines, tr, report, fname):
    changed = False
    for x in lines:
        en = tr.get(x['jp'])
        if en is None: continue
        b = encode(en)
        cap = x['len'] + x['pad'] - 1          # leave at least one NUL terminator
        if x.get('slot'): cap = x['slot'] - 1
        if len(b) > cap:
            report.append(f'TOO LONG ({len(b)}>{cap}) {fname}@{x["off"]:#x}: {en}')
            continue
        o = x['off']
        region = x['len']
        buf[o:o + max(region, len(b)) + 1] = b + b'\0' * (max(region, len(b)) + 1 - len(b))
        changed = True
    return changed

TABLE_OFF = 0x174930      # file table in SLPM_623.22: (name ptr, size, sum, xor)
VA_DELTA = 0x10f000       # data segment VA -> file offset

def checksum(d):
    n = len(d) // 4
    s = x = 0
    for v in struct.unpack_from(f'<{n}I', d):
        s = (s + v) & 0xFFFFFFFF; x ^= v
    return s, x

def update_checksum(elf, name, data, report):
    """The game sums/xors every u32 of a loaded file and hangs if it doesn't match."""
    o = TABLE_OFF; found = 0
    while True:
        p, size = struct.unpack_from('<II', elf, o)
        if not (0x500000 < p < 0x600000): break
        q = p - VA_DELTA
        if elf[q:elf.index(b'\0', q)].decode('ascii', 'replace') == name:
            s, x = checksum(data[:size])
            struct.pack_into('<II', elf, o + 8, s, x); found += 1
        o += 16
    report.append(f'checksum updated for {name} ({found} table entr{"y" if found == 1 else "ies"})')

def update_signature(elf, old, new, label, report):
    """Rows of (name ptr, size, sum, xor) exist for whole files AND for each PAC entry.
    Find every row describing `old` by its exact (size, sum, xor) and rewrite it for `new`."""
    s0, x0 = checksum(old)
    pat = struct.pack('<III', len(old), s0, x0)
    s1, x1 = checksum(new)
    rep = struct.pack('<III', len(new), s1, x1)
    n = 0; p = elf.find(pat)
    while p >= 0:
        elf[p:p + 12] = rep; n += 1
        p = elf.find(pat, p + 12)
    report.append(f'signature rows updated for {label}: {n}')
    if n == 0:
        report.append(f'WARNING: no signature row found for {label}')

def iso_record(iso, path):
    rec = iso.get_record(iso_path=path)
    return rec.extent_location(), rec.data_length

def patch_dir_record(isobytes, path_name, new_lba, new_size, old_lba):
    # find directory record with matching old extent and name, update LBA/size (both endian)
    name = path_name.encode()
    pos = 0
    while True:
        pos = isobytes.find(name, pos)
        if pos < 0: raise RuntimeError('dir record not found ' + path_name)
        start = pos - 33
        if start >= 0 and struct.unpack_from('<I', isobytes, start + 2)[0] == old_lba:
            struct.pack_into('<I', isobytes, start + 2, new_lba)
            struct.pack_into('>I', isobytes, start + 6, new_lba)
            struct.pack_into('<I', isobytes, start + 10, new_size)
            struct.pack_into('>I', isobytes, start + 14, new_size)
            return
        pos += 1

def main(orig_iso, lines_json, tr_tsv, out_iso):
    tr = load_tr(tr_tsv)
    lines = json.load(open(lines_json))
    by_file = {}
    for x in lines: by_file.setdefault(x['file'], []).append(x)
    report = []
    iso = pycdlib.PyCdlib(); iso.open(orig_iso)
    elf_lba, elf_size = iso_record(iso, '/SLPM_623.22;1')
    cn3_lba, cn3_size = iso_record(iso, '/PAC/CN3.PAC;1')
    iso.close()

    data = bytearray(open(orig_iso, 'rb').read())

    # --- main executable, patched in place
    elf = bytearray(data[elf_lba * SECTOR: elf_lba * SECTOR + elf_size])
    asciipatch.apply(elf)
    apply(elf, by_file.get('files/SLPM_623.22', []), tr, report, 'ELF')

    # --- CN3.PAC: patch decompressed entries, recompress, rebuild container
    cn3 = bytes(data[cn3_lba * SECTOR: cn3_lba * SECTOR + cn3_size])
    entries = pacmod.read_pac(cn3)
    blobs = []
    for k, (off, size) in enumerate(entries):
        raw = cn3[off:off + size]
        key = f'pac/CN3/{k:04d}.bin.dec' if raw[:4] == b'LZS\0' else f'pac/CN3/{k:04d}.bin'
        if key in by_file:
            dec = bytearray(lzs.decompress(raw) if raw[:4] == b'LZS\0' else raw)
            if apply(dec, by_file[key], tr, report, key):
                old_raw = raw
                raw = lzs_comp.compress(bytes(dec)) if raw[:4] == b'LZS\0' else bytes(dec)
                update_signature(elf, old_raw, raw, f'CN3 entry {k}', report)
        blobs.append(raw)
    # Prefer in-place: every entry keeps its offset if it still fits in its slot.
    out = bytearray(cn3)
    slots = [entries[k + 1][0] if k + 1 < len(entries) else len(cn3) for k in range(len(entries))]
    inplace = all(len(b) <= slots[k] - entries[k][0] for k, b in enumerate(blobs))
    if inplace:
        for k, b in enumerate(blobs):
            off = entries[k][0]
            out[off:slots[k]] = b + b'\0' * (slots[k] - off - len(b))
            struct.pack_into('<II', out, 12 + 8 * k, off, len(b))
    else:
        # Compact repack: same header, entries re-laid sequentially on 0x800 boundaries,
        # file padded back to its ORIGINAL size so the program's file table still matches.
        # Entries before the first overflow keep their exact offsets; from there on,
        # pack with 16-byte alignment (the game loads and checksums the whole file).
        first = next(k for k, b in enumerate(blobs) if len(b) > slots[k] - entries[k][0])
        out = bytearray(cn3[:entries[first][0]])
        for k in range(first):
            struct.pack_into('<II', out, 12 + 8 * k, entries[k][0], len(blobs[k]))
            out[entries[k][0]:entries[k][0] + len(blobs[k])] = blobs[k]
        for k in range(first, len(blobs)):
            b = blobs[k]
            off = len(out)
            struct.pack_into('<II', out, 12 + 8 * k, off, len(b))
            out += b
            out += b'\0' * ((-len(out)) % 0x10)
        if len(out) > len(cn3):
            raise SystemExit(f'CN3.PAC would grow by {len(out) - len(cn3)} bytes; shorten text in the overflowing entries')
        out += b'\0' * (len(cn3) - len(out))
        report.append(f'CN3 entries shifted to fit (file size unchanged, {len(cn3) - len(out.rstrip(bytes(1)))} bytes spare)')
    new_cn3 = bytes(out)
    if new_cn3 != cn3:
        update_checksum(elf, 'cn3.pac', new_cn3, report)
    data[elf_lba * SECTOR: elf_lba * SECTOR + elf_size] = elf

    if len(new_cn3) <= cn3_size:
        data[cn3_lba * SECTOR: cn3_lba * SECTOR + cn3_size] = new_cn3 + b'\0' * (cn3_size - len(new_cn3))
        patch_dir_record(data, 'CN3.PAC;1', cn3_lba, len(new_cn3), cn3_lba)
    else:
        new_lba = len(data) // SECTOR
        data += new_cn3 + b'\0' * ((-len(new_cn3)) % SECTOR)
        patch_dir_record(data, 'CN3.PAC;1', new_lba, len(new_cn3), cn3_lba)
        # update primary volume descriptor volume space size
        total = len(data) // SECTOR
        struct.pack_into('<I', data, 16 * SECTOR + 80, total)
        struct.pack_into('>I', data, 16 * SECTOR + 84, total)
        report.append(f'CN3.PAC relocated to LBA {new_lba} ({len(new_cn3)} bytes)')

    open(out_iso, 'wb').write(data)
    print('\n'.join(report) or 'all lines fit')

if __name__ == '__main__':
    main(*sys.argv[1:5])
