#!/bin/sh
# Build a playable CD image. Run from work/:  ../scripts/make.sh "The Conbini 3 (EN test 8)"
# Needs game.iso (2048-byte sectors) and orig.bin/orig.cue (raw CD) from the original disc.
set -e
here=$(dirname "$0")
python3 -I "$here/tr.py" check | tail -1
python3 -I "$here/build.py" game.iso new.iso
python3 -I "$here/cdsector.py" orig.bin new.iso new.bin
sed 's/orig.bin/new.bin/' orig.cue > new.cue
chdman createcd -i new.cue -o "../out/$1.chd" -f > /dev/null 2>&1
rm -f new.iso new.bin new.cue
echo "built ../out/$1.chd"
