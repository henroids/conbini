import struct, sys

# "LZS\0" + u32 decompressed size + Okumura-style LZSS stream.
def decompress(data, ring_init=0x00, start_pos=0xFEE):
    assert data[:4] == b'LZS\0'
    out_size = struct.unpack_from('<I', data, 4)[0]
    ring = bytearray([ring_init]) * 4096
    r = start_pos
    out = bytearray()
    i = 8
    flags = 0
    while len(out) < out_size and i < len(data):
        flags >>= 1
        if not flags & 0x100:
            flags = data[i] | 0xFF00; i += 1
        if flags & 1:
            c = data[i]; i += 1
            out.append(c); ring[r] = c; r = (r + 1) & 0xFFF
        else:
            if i + 1 >= len(data): break
            lo, hi = data[i], data[i + 1]; i += 2
            pos = lo | ((hi & 0xF0) << 4)
            ln = (hi & 0x0F) + 3
            for k in range(ln):
                c = ring[(pos + k) & 0xFFF]
                out.append(c); ring[r] = c; r = (r + 1) & 0xFFF
    return bytes(out[:out_size])

if __name__ == '__main__':
    d = decompress(open(sys.argv[1], 'rb').read())
    open(sys.argv[2], 'wb').write(d)
    print(len(d), d[:32].hex(' '))
