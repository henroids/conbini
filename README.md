# The Conbini 3 (ザコンビニ3) English Translation (PS2, SLPM-62322)

Fan translation of *The Conveni 3: Ano Machi o Dokusen seyo* into casual English, plus learning tools for studying the game's Japanese.

No game data lives in this repo. You need your own disc image.

## How the game stores text
- **SLPM_623.22** (main program): menus, help pages, item descriptions. Shift-JIS, NUL-terminated, in fixed slots. Edited in place.
- **PAC/CN3.PAC**: a `PAC` container (`"PAC\0"`, header size, count, then `(offset, size)` pairs). Most entries are `LZS` (LZSS, 4 KB window, ring start 0xFEE).
- Control codes inside strings: `/n` newline, `/r`, `/kA`/`/kB`, `/w`, `/I100` and `/I101` (memory card and slot names), `%s` and `%d`.
- The program has a built-in file table at file offset `0x174930`. Each entry is a name pointer, the size, then the 32-bit **sum** and **XOR** of every u32 word in the file. The game checks these on load and hangs on "Now Loading" if they don't match. A second table of the same row format (at `0x23c030`) covers each entry inside CN3.PAC, using the compressed size, sum and XOR. `build.py` finds every row matching a changed file or entry by its original (size, sum, xor) and rewrites it. Keep files at their original size and position.
- The text engine (draw `0x1bb910`, measure `0x1bc8c8`) reads every non-command byte as a 2-byte Shift-JIS code, so plain ASCII renders blank. `tools/asciipatch.py` hooks both routines (calls placed at `0x1bbed8` and `0x1bcc54`) and maps bytes below 0x80 to their full-width glyphs through a 96-entry table. The patch code lives in an unused debug-dump function at `0x199f50`.
- The game has 4 fonts, each with only the glyphs its screens need (glyph tables at VA `0x258bf0`, `0x263038`, `0x26bc50`, `0x276098`; entry -1 = missing). Font 1 has almost no Latin letters, so the patch falls back to font 0 for any ASCII glyph the current font lacks, restoring the font at the next character and on exit. In fixed-pitch mode (`0x420000-0xec0` nonzero) ASCII letters advance by their own width and spaces by half the pitch.
- Extra codes: `/w` small spacer, `/0`-`/9` value inserts, `/N` newline. No apostrophe glyph exists in any font.
- Engine commands: a bare `/`, `<` or `>` triggers a control code, so prose uses the full-width forms. Some helpers walk text 2 bytes at a time, so every control code must start at an even byte offset and every string must have even length (`build.py` pads with spaces).

## Tools
| script | purpose |
|---|---|
| `tools/pac.py` | unpack a PAC container |
| `tools/lzs.py` / `tools/lzs_comp.py` | LZS decompress / compress (best-size parse, slightly smaller than the original files) |
| `tools/extract.py`, `tools/clean.py` | dump the Japanese strings with their offsets and slot sizes |
| `tools/build.py` | apply `translations.tsv` (jp⇥en) to a 2048-byte ISO, keeping everything in place |
| `tools/cdsector.py` | write the result back into the raw MODE2/2352 image with correct EDC/ECC |

## Build
```
chdman extractcd -i game.chd -o orig.cue -ob orig.bin
# convert orig.bin to a 2048-byte game.iso (user data at offset 24 of each sector)
python3 tools/build.py game.iso lines.json translations.tsv patched.iso
python3 tools/cdsector.py orig.bin patched.iso patched.bin
chdman createcd -i patched.cue -o "The Conbini 3 (EN).chd"
```
