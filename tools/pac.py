import struct, sys, os

# PAC container: "PAC\0", u32 header_size, u32 count, then count x (u32 offset, u32 size)
def read_pac(data):
    assert data[:4] == b'PAC\0', 'not a PAC'
    hsize, count = struct.unpack_from('<II', data, 4)
    entries = []
    for k in range(count):
        off, size = struct.unpack_from('<II', data, 12 + 8 * k)
        entries.append((off, size))
    return entries

if __name__ == '__main__':
    src, outdir = sys.argv[1], sys.argv[2]
    data = open(src, 'rb').read()
    os.makedirs(outdir, exist_ok=True)
    for k, (off, size) in enumerate(read_pac(data)):
        chunk = data[off:off + size]
        open(os.path.join(outdir, f'{k:04d}.bin'), 'wb').write(chunk)
        print(k, hex(off), size, chunk[:16].hex(' '))
