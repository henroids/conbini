"""Code patch: let the game draw single-byte ASCII by mapping it to full-width glyphs.

The text engine reads every non-special byte as a 2-byte Shift-JIS code
(draw routine 0x1bb910, measure routine 0x1bc8c8). We hook the spot where each
builds that code. For bytes < 0x80 the hook returns the full-width equivalent
from a lookup table and steps the string pointer back one byte, so the engine's
normal "+2" advance becomes "+1".

Code + table live in an unused debug-dump function at 0x199f50.
"""
import struct
from keystone import Ks, KS_ARCH_MIPS, KS_MODE_MIPS64, KS_MODE_LITTLE_ENDIAN

VA_TO_FILE = 0x10f000          # text segment: file offset = VA - 0x10f000
CAVE = 0x199f50
CAVE_SIZE = 0x8c8

def _ks():
    return Ks(KS_ARCH_MIPS, KS_MODE_MIPS64 + KS_MODE_LITTLE_ENDIAN)

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

FONT_BYTE = -0xe58    # (0x420000 + this) = current font index
FONT_TABLES = 0x4e0   # (0x280000 + this)[font] = glyph table; entry -1 = glyph missing
# idx = code - 0x813f for all codes we produce

LOOKUP = """
    lui   $t9, %TB_HI%
    addiu $t9, $t9, %TB_LO%
    addiu $v0, $v0, -0x20
    sltiu $v1, $v0, 0x60
    beqz  $v1, {bad}
    sll   $v0, $v0, 1
    addu  $t9, $t9, $v0
    lhu   $v1, 0($t9)
"""
# check: glyph v1 missing in font REG (t9 clobbered) -> branch to {present} if present
HASGLYPH = """
    sll   $v0, {reg}, 2
    lui   $t9, 0x28
    addu  $t9, $t9, $v0
    lw    $t9, 0x4e0($t9)
    ori   $v0, $zero, 0x813f
    subu  $v0, $v1, $v0
    sll   $v0, $v0, 2
    addu  $t9, $t9, $v0
    lb    $t9, 0($t9)
    addiu $v0, $zero, -1
"""

SRC = """
cave_d:
    lui   $t8, %SV_HI%
    lbu   $t9, %SV_LO%($t8)
    sltiu $v0, $t9, 0xff
    beqz  $v0, d1
    sb    $t9, -0xe58($a2)
    move  $a0, $t9
    addiu $v0, $zero, 0xff
    sb    $v0, %SV_LO%($t8)
d1:
    lbu   $v0, 0($s1)
    sltiu $t9, $v0, 0x80
    bnez  $t9, asc_d
    lbu   $v1, 1($s1)
    sb    $zero, %FL_LO%($t8)
    sll   $v0, $v0, 8
    addu  $v1, $v1, $v0
    jr    $ra
asc_d:
    addiu $s1, $s1, -1
    addiu $t9, $zero, 1
    sb    $t9, %FL_LO%($t8)
""" + LOOKUP.format(bad='bad_d') + """
    beqz  $a0, done_d
""" + HASGLYPH.format(reg='$a0') + """
    bne   $t9, $v0, done_d
""" + HASGLYPH.format(reg='$zero') + """
    beq   $t9, $v0, done_d
    sb    $a0, %SV_LO%($t8)
    sb    $zero, -0xe58($a2)
    move  $a0, $zero
done_d:
    move  $v0, $zero
    jr    $ra
bad_d:
    ori   $v1, $zero, 0x8140
    move  $v0, $zero
    jr    $ra

cave_m:
    lui   $t8, %SV_HI%
    lbu   $t9, %SV_LO%($t8)
    sltiu $v1, $t9, 0xff
    beqz  $v1, m1
    sb    $t9, -0xe58($10)
    addiu $v1, $zero, 0xff
    sb    $v1, %SV_LO%($t8)
m1:
    sltiu $t9, $v0, 0x80
    bnez  $t9, asc_m
    lbu   $v1, 1($s0)
    sb    $zero, %FL_LO%($t8)
    sll   $v0, $v0, 8
    addu  $v1, $v1, $v0
    jr    $ra
asc_m:
    addiu $s0, $s0, -1
    addiu $t9, $zero, 1
    sb    $t9, %FL_LO%($t8)
""" + LOOKUP.format(bad='bad_m') + """
    lbu   $v0, -0xe58($10)
    beqz  $v0, done_m
    sll   $v0, $v0, 2
    lui   $t9, 0x28
    addu  $t9, $t9, $v0
    lw    $t9, 0x4e0($t9)
    ori   $v0, $zero, 0x813f
    subu  $v0, $v1, $v0
    sll   $v0, $v0, 2
    addu  $t9, $t9, $v0
    lb    $t9, 0($t9)
    addiu $v0, $zero, -1
    bne   $t9, $v0, done_m
""" + HASGLYPH.format(reg='$zero') + """
    beq   $t9, $v0, done_m
    lbu   $t9, -0xe58($10)
    sb    $t9, %SV_LO%($t8)
    sb    $zero, -0xe58($10)
done_m:
    move  $v0, $zero
    jr    $ra
bad_m:
    ori   $v1, $zero, 0x8140
    move  $v0, $zero
    jr    $ra

restore_x:
    lui   $t8, %SV_HI%
    lbu   $t9, %SV_LO%($t8)
    sltiu $v1, $t9, 0xff
    beqz  $v1, rx_end
    lui   $v1, 0x42
    sb    $t9, -0xe58($v1)
    addiu $t9, $zero, 0xff
    sb    $t9, %SV_LO%($t8)
rx_end:
    jr    $ra
restore_d:
    ld    $s0, 0xe0($sp)
    b     restore_x
restore_m:
    ld    $s0, 0x50($sp)
    b     restore_x

adv_d:
    lhu   $a3, -0xee8($a3)
    beqz  $a0, ad_end
    lui   $t8, %SV_HI%
    lbu   $t9, %FL_LO%($t8)
    beqz  $t9, ad_end
    addu  $a2, $a1, $a3
ad_end:
    jr    $ra
adv_m:
    lhu   $8, -0xee8($8)
    beqz  $a0, am_end
    lui   $t8, %SV_HI%
    lbu   $t9, %FL_LO%($t8)
    beqz  $t9, am_end
    addu  $a2, $a3, $8
am_end:
    jr    $ra
"""

LABELS = ['cave_d', 'cave_m', 'restore_d', 'restore_m', 'adv_d', 'adv_m']

def _hilo(va):
    hi = (va + 0x8000) >> 16
    return hi, va - (hi << 16)

def build_cave():
    def fill(src, tb, sv, fl):
        th, tl = _hilo(tb); sh, sl = _hilo(sv); fh, fl2 = _hilo(fl)
        assert sh == fh
        return (src.replace('%TB_HI%', hex(th)).replace('%TB_LO%', str(tl))
                   .replace('%SV_HI%', hex(sh)).replace('%SV_LO%', str(sl)).replace('%FL_LO%', str(fl2)))
    probe = asm(fill(SRC, CAVE, CAVE, CAVE), CAVE)
    table_va = CAVE + ((len(probe) + 15) & ~15)
    flag_va = table_va + 0xc0
    saved_va = flag_va + 1
    code = asm(fill(SRC, table_va, saved_va, flag_va), CAVE)
    assert len(code) == len(probe)
    addr = {}
    for lab in LABELS:
        part = SRC[:SRC.index(lab + ':')]
        addr[lab] = CAVE + len(asm(fill(part + '\nzz:\n nop\n', table_va, saved_va, flag_va), CAVE)) - 4
    blob = code + b'\0' * (table_va - CAVE - len(code)) + table_bytes() + bytes([0, 0xff])
    assert len(blob) <= CAVE_SIZE
    return blob, addr

NOP = b'\0\0\0\0'
SPACE_WIDTH = 7

def apply(elf):
    """Patch a bytearray holding SLPM_623.22 in place."""
    blob, addr = build_cave()
    f = CAVE - VA_TO_FILE
    elf[f:f + len(blob)] = blob

    def put(va, data):
        o = va - VA_TO_FILE
        elf[o:o + len(data)] = data
    def jal(va, target):
        put(va, asm(f'jal {target:#x}', va)[:4])

    # read char (draw / measure)
    jal(0x1bbed8, addr['cave_d']); put(0x1bbee4, NOP); put(0x1bbee8, NOP); put(0x1bbef4, NOP)
    jal(0x1bcc54, addr['cave_m']); put(0x1bcc5c, NOP); put(0x1bcc64, NOP)
    # restore font on exit (original first epilogue load is redone in the cave)
    jal(0x1bc680, addr['restore_d'])
    jal(0x1bcfa0, addr['restore_m'])
    # fixed-pitch: letters advance by their own width
    jal(0x1bc3e4, addr['adv_d'])
    jal(0x1bce7c, addr['adv_m'])

    # half-width space: ASCII 0x20 advances by 15px (same as a kanji); make it 7px.
    for va in (0x1bb9f0, 0x1bba2c, 0x1bc920, 0x1bc95c):
        o = va - VA_TO_FILE
        assert elf[o:o + 2] == b'\x0f\x00', hex(va)
        elf[o:o + 2] = struct.pack('<H', SPACE_WIDTH)
    # fixed-pitch space: half the pitch (delay slots "move a0, v1" -> "srl a0, v1, 1")
    put(0x1bb9fc, asm('srl $a0, $v1, 1', 0x1bb9fc))
    put(0x1bc92c, asm('srl $a0, $v1, 1', 0x1bc92c))

if __name__ == '__main__':
    blob, addr = build_cave()
    print({k: hex(v) for k, v in addr.items()}, len(blob), 'bytes')
