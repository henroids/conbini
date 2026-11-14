"""Disassembly helpers for the main program: dis VA [N], xref VA."""
import struct, sys
from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS64, CS_MODE_LITTLE_ENDIAN
BASE = 0x10f000
ELF = open('files/SLPM_623.22', 'rb').read()
TEXT_END = 0x400000 - BASE
md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS64 | CS_MODE_LITTLE_ENDIAN)

def dis(va, n=40):
    for a in range(va, va + 4 * n, 4):
        i = next(md.disasm(ELF[a - BASE:a - BASE + 4], a), None)
        print(f'{a:x}: {i.mnemonic} {i.op_str}' if i else f'{a:x}: ?')

def xref(va):
    """Find lui/addiu (or ori) pairs and jal targets resolving to va, plus raw pointers."""
    hi, lo = (va + 0x8000) >> 16, va & 0xffff
    out = []
    w = struct.unpack_from(f'<{TEXT_END // 4}I', ELF, 0)
    for k, x in enumerate(w):
        if x >> 26 == 3 and (x & 0x3ffffff) << 2 == va:
            out.append(('jal', k * 4 + BASE))
        if x >> 26 in (9, 25, 13) and x & 0xffff == lo:
            rs = (x >> 21) & 31
            for j in range(k - 1, max(k - 12, 0), -1):
                y = w[j]
                if y >> 26 == 15 and (y >> 16) & 31 == rs:
                    if y & 0xffff == (hi if x >> 26 != 13 else va >> 16):
                        out.append(('ref', k * 4 + BASE))
                    break
    p = struct.pack('<I', va); i = ELF.find(p, TEXT_END)
    while i >= 0:
        out.append(('ptr', i + BASE)); i = ELF.find(p, i + 1)
    return out

if __name__ == '__main__':
    a = sys.argv
    if a[1] == 'dis': dis(int(a[2], 16), int(a[3]) if len(a) > 3 else 40)
    else:
        for t, v in xref(int(a[2], 16)): print(t, hex(v))
