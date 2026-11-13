"""Code patch: let the game draw single-byte ASCII by mapping it to full-width glyphs.

The text engine reads every non-special byte as a 2-byte Shift-JIS code
(draw routine 0x1bb910, measure routine 0x1bc8c8). We hook the spot where each
builds that code. For bytes < 0x80 the hook returns the full-width equivalent
from a lookup table and steps the string pointer back one byte, so the engine's
normal "+2" advance becomes "+1".

Code + table live in an unused debug-dump function at 0x199f50.
"""
import struct
from keystone import Ks, KS_ARCH_MIPS, KS_MODE_MIPS32, KS_MODE_LITTLE_ENDIAN

VA_TO_FILE = 0x10f000          # text segment: file offset = VA - 0x10f000
CAVE = 0x199f50
CAVE_SIZE = 0x8c8

def _ks():
    return Ks(KS_ARCH_MIPS, KS_MODE_MIPS32 + KS_MODE_LITTLE_ENDIAN)

def asm(src, addr):
    enc, _ = _ks().asm(src, addr)
    return bytes(enc)

def table_bytes():
    out = bytearray()
    special = {' ': '　', '"': '”', "'": '’', '-': '－', '~': '～',
               '\\': '＼', '`': '｀', '^': '＾', '|': '｜', '_': '＿'}
    for c in range(0x20, 0x80):
        ch = chr(c)
        if ch in special: fw = special[ch]
        elif 0x21 <= c <= 0x7e: fw = chr(c + 0xFEE0)
        else: fw = '　'
        code = fw.encode('cp932')
        assert len(code) == 2, (ch, code)
        out += struct.pack('<H', (code[0] << 8) | code[1])
    return bytes(out)

PART_D = """
    lbu   $v0, 0($s1)
    sltiu $t9, $v0, 0x80
    bnez  $t9, asc_d
    lbu   $v1, 1($s1)
    sll   $v0, $v0, 8
    addu  $v1, $v1, $v0
    jr    $ra
asc_d:
    addiu $s1, $s1, -1
    b     conv
"""
PART_M = """
cave_m:
    sltiu $t9, $v0, 0x80
    bnez  $t9, asc_m
    lbu   $v1, 1($s0)
    sll   $v0, $v0, 8
    addu  $v1, $v1, $v0
    jr    $ra
asc_m:
    addiu $s0, $s0, -1
"""
PART_C = """
conv:
    lui   $t8, %HI%
    addiu $t8, $t8, %LO%
    addiu $t9, $v0, -0x20
    sltiu $v1, $t9, 0x60
    beqz  $v1, bad
    sll   $t9, $t9, 1
    addu  $t8, $t8, $t9
    lhu   $v1, 0($t8)
    move  $v0, $zero
    jr    $ra
bad:
    ori   $v1, $zero, 0x8140
    move  $v0, $zero
    jr    $ra
"""

def build_cave():
    src = PART_D + PART_M + PART_C
    probe = asm(src.replace('%HI%', '0').replace('%LO%', '0'), CAVE)
    table_va = CAVE + ((len(probe) + 15) & ~15)
    hi = (table_va + 0x8000) >> 16
    lo = table_va - (hi << 16)
    code = asm(src.replace('%HI%', hex(hi)).replace('%LO%', str(lo)), CAVE)
    assert len(code) == len(probe)
    # address of cave_m = length of the PART_D code (labels resolved within it)
    part_d = asm(PART_D + '\nconv:\n    nop\n', CAVE)
    cave_m = CAVE + len(part_d) - 4
    blob = code + b'\0' * (table_va - CAVE - len(code)) + table_bytes()
    assert len(blob) <= CAVE_SIZE
    return blob, CAVE, cave_m

NOP = b'\0\0\0\0'
SPACE_WIDTH = 7

def apply(elf):
    """Patch a bytearray holding SLPM_623.22 in place."""
    blob, cave_d, cave_m = build_cave()
    f = CAVE - VA_TO_FILE
    elf[f:f + len(blob)] = blob

    def put(va, data):
        o = va - VA_TO_FILE
        elf[o:o + len(data)] = data

    # draw routine: replace 2-byte read with call to cave_d
    put(0x1bbed8, asm(f'jal {cave_d:#x}', 0x1bbed8)[:4])
    put(0x1bbee4, NOP)       # lbu v1,1(s1)
    put(0x1bbee8, NOP)       # sll v0,v0,8
    put(0x1bbef4, NOP)       # addu v1,v1,v0
    # measure routine
    put(0x1bcc54, asm(f'jal {cave_m:#x}', 0x1bcc54)[:4])
    put(0x1bcc5c, NOP)       # sll v0,v0,8
    put(0x1bcc64, NOP)       # addu v1,v1,v0

    # half-width space: ASCII 0x20 advances by 15px (same as a kanji); make it 7px.
    # (full-width space 0x8140 uses separate constants and is left alone)
    for va in (0x1bb9f0, 0x1bba2c, 0x1bc920, 0x1bc95c):
        o = va - VA_TO_FILE
        assert elf[o:o + 2] == b'\x0f\x00', hex(va)
        elf[o:o + 2] = struct.pack('<H', SPACE_WIDTH)

if __name__ == '__main__':
    blob, d, m = build_cave()
    from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS64, CS_MODE_LITTLE_ENDIAN
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS64 + CS_MODE_LITTLE_ENDIAN)
    for i in md.disasm(blob[:0x90], CAVE):
        print(hex(i.address), i.mnemonic, i.op_str)
    print('cave_m at', hex(m), 'blob', len(blob), 'bytes')
