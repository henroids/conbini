"""Build the translated disc image. Run from work/:

    python3 -I ../scripts/build.py game.iso out.iso

Text is written over the Japanese in place (lines.json says where every copy is),
the main program gets the engine patches, and CN3.PAC is recompressed. No file moves
or changes size, so the disc layout is untouched.
"""
import hashlib, json, os, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
import pycdlib, lzs, lzs_comp, pac, patch, tr

SECTOR = 2048
ELF, CN3 = '/SLPM_623.22;1', '/PAC/CN3.PAC;1'

def write_text(buf, lines, table):
    """Overwrite each translated string; returns how many were written."""
    n = 0
    for x in lines:
        b = table.get(x['jp'])
        if b is None:
            continue
        if len(b) > x['len'] + x['pad'] - 1:                 # keep one NUL terminator
            print(f'does not fit at {x["file"]}@{x["off"]:#x}: {b.decode("cp932")}')
            continue
        size = max(x['len'], len(b)) + 1
        buf[x['off']:x['off'] + size] = b.ljust(size, b'\0')
        n += 1
    return n

def signature(d):
    """(size, sum, xor) over the u32s of a file: the game hangs on load if these differ."""
    s = x = 0
    for v in struct.unpack_from(f'<{len(d) // 4}I', d):
        s = (s + v) & 0xffffffff; x ^= v
    return struct.pack('<III', len(d), s, x)

def resign(elf, old, new, what):
    """The program holds a signature row for every file and every CN3 entry."""
    a, b = signature(old), signature(new)
    n = elf.count(a)
    assert n, f'no signature row for {what}'
    elf[:] = elf.replace(a, b)

def compress(data):
    """LZS-compress, remembering results in cache/ (compression is the slow step)."""
    path = 'cache/' + hashlib.sha1(data).hexdigest()
    if not os.path.exists(path):
        os.makedirs('cache', exist_ok=True)
        open(path, 'wb').write(lzs_comp.compress(data))
    return open(path, 'rb').read()

def rebuild_cn3(cn3, lines, table, elf):
    """Patch and recompress entries. An entry stays at its offset when it can; one that
    has grown pushes the following entries along until the slack is used up."""
    entries = pac.read_pac(cn3)
    out = bytearray(len(cn3))
    cursor = entries[0][0]
    out[:cursor] = cn3[:cursor]
    for k, (off, size) in enumerate(entries):
        raw = cn3[off:off + size]
        packed = raw[:4] == b'LZS\0'
        name = f'pac/CN3/{k:04d}.bin' + ('.dec' if packed else '')
        if name in lines:
            data = bytearray(lzs.decompress(raw) if packed else raw)
            if write_text(data, lines[name], table):
                new = compress(bytes(data)) if packed else bytes(data)
                resign(elf, raw, new, f'CN3 entry {k}')
                raw = new
        off = off if cursor <= off else cursor + (-cursor) % 16
        if off + len(raw) > len(cn3):
            raise SystemExit(f'CN3.PAC is full at entry {k}: shorten some text')
        out[off:off + len(raw)] = raw
        struct.pack_into('<II', out, 12 + 8 * k, off, len(raw))
        cursor = off + len(raw)
    print(f'CN3.PAC: {len(cn3) - cursor} bytes spare')
    resign(elf, cn3, out, 'CN3.PAC')
    return out

def main(src, dst):
    iso = pycdlib.PyCdlib(); iso.open(src)
    where = {}
    for path in (ELF, CN3):
        rec = iso.get_record(iso_path=path)
        where[path] = slice(rec.extent_location() * SECTOR,
                            rec.extent_location() * SECTOR + rec.data_length)
    iso.close()

    table = tr.table()
    lines = {}
    for x in json.load(open('lines.json')):
        lines.setdefault(x['file'], []).append(x)

    disc = bytearray(open(src, 'rb').read())
    elf = bytearray(disc[where[ELF]])
    patch.apply(elf)
    n = write_text(elf, lines['files/SLPM_623.22'], table)
    print(f'main program: {n} strings')
    disc[where[CN3]] = rebuild_cn3(bytes(disc[where[CN3]]), lines, table, elf)
    disc[where[ELF]] = elf
    open(dst, 'wb').write(disc)

if __name__ == '__main__':
    main(*sys.argv[1:3])
