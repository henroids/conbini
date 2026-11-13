"""Merge id<TAB>text lines from stdin into en.tsv (overwrites same ids)."""
import sys
W='/home/claude/conbini/work/en.tsv'
d={}
for line in open(W,encoding='utf-8'):
    k,_,v=line.rstrip('\n').partition('\t'); d[int(k)]=v
for line in sys.stdin:
    line=line.rstrip('\n')
    if not line.strip(): continue
    k,_,v=line.partition('\t'); d[int(k)]=v
with open(W,'w',encoding='utf-8') as f:
    for k in sorted(d): f.write(f'{k}\t{d[k]}\n')
