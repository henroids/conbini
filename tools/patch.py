"""Engine patches for SLPM_623.22 so the game can show plain single-byte English.

1. Text engine (draw 0x1bb910, measure 0x1bc8c8) reads every character as a 2-byte
   Shift-JIS code. `rd_draw` / `rd_meas` replace that read: a byte < 0x80 is mapped to
   its full-width code through a table and the string pointer is stepped back one, so
   the engine's "+2" becomes "+1". If the current font lacks the glyph (font 1 has
   almost no Latin letters) the font is switched to font 0 for that one character.
2. Fixed-pitch mode: letters advance by their own width and are not centred in a cell.
3. Speech bubbles (0x1927f0) lay text out themselves, one record per 2-byte character.
   `bub` adds single-byte letters and word wrap; "/n" acts as a space there.

All code and data live in an unused debug-dump function (CAVE).
keystone adds the delay-slot NOP after every branch/jump itself.
"""
import re, struct
from keystone import Ks, KS_ARCH_MIPS, KS_MODE_MIPS64, KS_MODE_LITTLE_ENDIAN

BASE = 0x10f000                # file offset = VA - BASE
CAVE, CAVE_SIZE = 0x199f50, 0x8c8
SPACE = 7                      # width of an ASCII space in normal text
FONT = '-0xe58'                # (0x420000 + this) = current font index (byte)
_ks = Ks(KS_ARCH_MIPS, KS_MODE_MIPS64 + KS_MODE_LITTLE_ENDIAN)

def asm(src, addr):
    """Assemble; numeric local labels (1: ... 1f / 1b) become plain labels for keystone."""
    src = re.sub(r'^(\d):', r'L\1:', src, flags=re.M)
    src = re.sub(r'\b(\d)[fb]\b', r'L\1', src)
    return bytes(_ks.asm(src, addr)[0])

def table():
    """0x20..0x7f -> full-width Shift-JIS code (big-endian value in a u16)."""
    special = {' ': '　', '"': '”', "'": '’', '-': '－', '~': '～', '\\': '＼', '`': '｀',
               '^': '＾', '|': '｜', '_': '＿', '\x7f': '　'}
    out = b''
    for c in map(chr, range(0x20, 0x80)):
        hi, lo = special.get(c, chr(ord(c) + 0xfee0)).encode('cp932')
        out += struct.pack('<H', hi << 8 | lo)
    return out

# $t9 = first byte of glyph v1's entry in a font's table (-1 = missing), $v0 = -1
GLYPH = """
    lw    $t9, 0x4e0($t9)
    ori   $v0, $zero, 0x813f
    subu  $v0, $v1, $v0
    sll   $v0, $v0, 2
    addu  $t9, $t9, $v0
    lb    $t9, 0($t9)
    addiu $v0, $zero, -1
"""

def reader(ptr, load, font_in_a0):
    """Read one character at `ptr` -> v1 = code. The draw routine also keeps the font in a0."""
    a0_restore = 'move $a0, $t9' if font_in_a0 else ''
    a0_zero = 'move $a0, $zero' if font_in_a0 else ''
    return f"""
    lui   $t8, {{d_hi}}
    lbu   $t9, {{sv}}($t8)
    sltiu $v1, $t9, 0xff
    beqz  $v1, 1f
    lui   $v1, 0x42
    sb    $t9, {FONT}($v1)
    {a0_restore}
    addiu $v1, $zero, 0xff
    sb    $v1, {{sv}}($t8)
1:  {'lbu $v0, 0(' + ptr + ')' if load else ''}
    sltiu $t9, $v0, 0x80
    bnez  $t9, 2f
    lbu   $v1, 1({ptr})
    sb    $zero, {{fl}}($t8)
    sll   $v0, $v0, 8
    addu  $v1, $v1, $v0
    jr    $ra
2:  addiu {ptr}, {ptr}, -1
    addiu $t9, $zero, 1
    sb    $t9, {{fl}}($t8)
    sltiu $t9, $v0, 0x20
    beqz  $t9, 5f
    addiu $v0, $zero, 0x20
5:  sll   $v0, $v0, 1
    addu  $t9, $t8, $v0
    lhu   $v1, {{tb}}($t9)
    lui   $t9, 0x42
    lbu   $v0, {FONT}($t9)
    beqz  $v0, 4f
    addiu $t9, $v0, -1
    beqz  $t9, 3f
    sll   $v0, $v0, 2
    lui   $t9, 0x28
    addu  $t9, $t9, $v0
    {GLYPH}
    bne   $t9, $v0, 4f
3:  lui   $t9, 0x28
    {GLYPH}
    beq   $t9, $v0, 4f
    lui   $t9, 0x42
    lbu   $v0, {FONT}($t9)
    sb    $v0, {{sv}}($t8)
    sb    $zero, {FONT}($t9)
    {a0_zero}
4:  move  $v0, $zero
    jr    $ra
"""

ROUTINES = {
'rd_draw': reader('$s1', True, True),
'rd_meas': reader('$s0', False, False),

# put back the font a fallback replaced; s0 is the epilogue load the hook displaced
'restore': f"""
    lui   $t8, {{d_hi}}
    lbu   $t9, {{sv}}($t8)
    sltiu $v1, $t9, 0xff
    beqz  $v1, 1f
    lui   $v1, 0x42
    sb    $t9, {FONT}($v1)
    addiu $t9, $zero, 0xff
    sb    $t9, {{sv}}($t8)
1:  jr    $ra
""",
'end_draw': "ld $s0, 0xe0($sp)\n j {restore}",
'end_meas': "ld $s0, 0x50($sp)\n j {restore}",

# fixed pitch (a0 = pitch): a letter advances by its own width (+ font spacing)
'adv_draw': """
    lhu   $a3, -0xee8($a3)
    beqz  $a0, 1f
    lui   $t8, {d_hi}
    lbu   $t9, {fl}($t8)
    beqz  $t9, 1f
    addu  $a2, $a1, $a3
1:  jr    $ra
""",
'adv_meas': """
    lhu   $8, -0xee8($8)
    beqz  $a0, 1f
    lui   $t8, {d_hi}
    lbu   $t9, {fl}($t8)
    beqz  $t9, 1f
    addu  $a2, $a3, $8
1:  jr    $ra
""",
# fixed pitch: v0 = (pitch - glyph width), halved by the caller to centre; 0 for letters
'centre': """
    lbu   $v0, 3($a3)
    subu  $v0, $v1, $v0
    lui   $t8, {d_hi}
    lbu   $t9, {fl}($t8)
    beqz  $t9, 1f
    move  $v0, $zero
1:  jr    $ra
""",

# bubble: v0 = ASCII byte -> t8 = code, v1 = advance in the bubble font (font 2)
'bub_w': """
    addiu $t9, $v0, -0x2c
    bnez  $t9, 1f
    ori   $t8, $zero, 0x8141
    b     2f
1:  sll   $t9, $v0, 1
    lui   $t8, {d_hi}
    addu  $t8, $t8, $t9
    lhu   $t8, {tb}($t8)
2:  lui   $t9, 0x28
    lw    $t9, 0x4e8($t9)
    ori   $v1, $zero, 0x813f
    subu  $v1, $t8, $v1
    sll   $v1, $v1, 2
    addu  $t9, $t9, $v1
    lb    $v1, 0($t9)
    addiu $v1, $v1, 1
    beqz  $v1, 3f
    lbu   $v1, 3($t9)
    addiu $v1, $v1, 2
    jr    $ra
3:  addiu $v1, $zero, 0x1c
    jr    $ra
""",
# bubble layout loop: a0 = next byte. Letters get a record like the 2-byte path makes
# (s3 = record index, s7 = pen x, s5 = line width, s2 = string index, s4 = string).
'bub': """
    addiu $v0, $a0, -0x20
    sltiu $v1, $v0, 0x5f
    beqz  $v1, 9f
    beqz  $v0, 5f
    addiu $v1, $a0, -0x2f
    beqz  $v1, 9f
    move  $v0, $a0
    jal   {bub_w}
    addiu $a2, $30, -0x58b0
    sll   $a0, $s3, 2
    addu  $a0, $a0, $s3
    sll   $a0, $a0, 3
    lw    $a1, 0x958($a2)
    addu  $a1, $a1, $a0
    srl   $v0, $t8, 8
    sb    $v0, 0x1c($a1)
    sb    $t8, 0x1d($a1)
    lw    $v0, 0x28($sp)
    sb    $v0, 0x24($a1)
    addiu $v0, $s7, 2
    sh    $v0, 0xe($a1)
    lw    $v0, 0x30($sp)
    sh    $v0, 0x10($a1)
    addiu $s2, $s2, 1
    addu  $s7, $s7, $v1
    j     0x1929e4
5:  addiu $s2, $s2, 1
    j     {bub_gap}
9:  lui   $ra, 0x19
    ori   $ra, $ra, 0x2950
    j     0x18e130
""",
# a space (or "/n"): start a new line if the next word would not fit, else leave a gap
'bub_gap': """
    addu  $a0, $s4, $s2
    move  $a1, $zero
1:  lbu   $v0, 0($a0)
    addiu $v1, $v0, -0x21
    sltiu $v1, $v1, 0x5e
    beqz  $v1, 2f
    addiu $v1, $v0, -0x2f
    beqz  $v1, 2f
    jal   {bub_w}
    addu  $a1, $a1, $v1
    addiu $a0, $a0, 1
    b     1b
2:  addiu $v0, $s7, -10
    beqz  $v0, 4f
    addiu $v0, $s7, 40
    addu  $v0, $v0, $a1
    slt   $v0, $s5, $v0
    beqz  $v0, 3f
    j     0x192e70
3:  addiu $s7, $s7, 12
4:  j     0x1930e8
""",
}

def build():
    """Assemble the cave. Two passes: sizes first, then real addresses."""
    sym = dict.fromkeys(ROUTINES, CAVE) | {'d_hi': 0, 'tb': 0, 'fl': 0, 'sv': 0}
    for _ in range(2):
        addr, parts = CAVE, []
        for name, src in ROUTINES.items():
            sym[name] = addr
            parts.append(asm(src.format_map({k: f'{v:#x}' if k in ROUTINES else str(v)
                                             for k, v in sym.items()}), addr))
            addr += len(parts[-1])
        data = (addr + 3) & ~3                       # table, then flag byte, saved-font byte
        hi = (data + 0x8000) >> 16
        lo = data - (hi << 16)
        sym |= {'d_hi': hi, 'tb': lo - 0x40, 'fl': lo + 0xc0, 'sv': lo + 0xc1}
        assert -0x8000 <= lo - 0x40 and lo + 0xc1 < 0x8000
    blob = b''.join(parts).ljust(data - CAVE, b'\0') + table() + b'\x00\xff'
    assert len(blob) <= CAVE_SIZE, len(blob)
    return blob, sym

def apply(elf):
    """Patch a bytearray holding SLPM_623.22 in place."""
    blob, sym = build()

    def put(va, data, expect=None):
        o = va - BASE
        assert expect is None or elf[o:o + len(expect)] == expect, hex(va)
        elf[o:o + len(data)] = data
    def ins(va, src):                                # one instruction, keeping the delay slot
        put(va, asm(src, va)[:4])
    nop = lambda *vas: [put(va, bytes(4)) for va in vas]

    put(CAVE, blob)
    ins(0x1bbed8, f'jal {sym["rd_draw"]}'); nop(0x1bbee4, 0x1bbee8, 0x1bbef4)
    ins(0x1bcc54, f'jal {sym["rd_meas"]}'); nop(0x1bcc5c, 0x1bcc64)
    ins(0x1bc680, f'jal {sym["end_draw"]}')
    ins(0x1bcfa0, f'jal {sym["end_meas"]}')
    ins(0x1bc3e4, f'jal {sym["adv_draw"]}')
    ins(0x1bce7c, f'jal {sym["adv_meas"]}')
    ins(0x1bc27c, f'jal {sym["centre"]}')            # returns onto the original "srl s4, v0, 1"

    # an ASCII space is 15px wide (a kanji cell), or one full cell in fixed pitch: narrow both
    for va in (0x1bb9f0, 0x1bba2c, 0x1bc920, 0x1bc95c):
        put(va, struct.pack('<H', SPACE), b'\x0f\x00')
    for va in (0x1bb9fc, 0x1bc92c):
        ins(va, f'addiu $a0, $zero, {SPACE}')

    ins(0x192948, f'j {sym["bub"]}')
    put(0x537a60 + 4 * (ord('N') - ord('C')), struct.pack('<I', sym['bub_gap']),
        struct.pack('<I', 0x1930e8))                 # "/n" was ignored in bubbles
    # record counter: count 1-byte letters too (retarget "bne v1, v0" from skip to count)
    put(0x195858, struct.pack('<H', (0x1958bc - 0x19585c) // 4), struct.pack('<H', (0x1958e4 - 0x19585c) // 4))

if __name__ == '__main__':
    blob, sym = build()
    print(len(blob), 'of', CAVE_SIZE, 'bytes;', {k: hex(v) for k, v in sym.items() if k in ROUTINES})
