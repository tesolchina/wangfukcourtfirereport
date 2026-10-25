import re, json, sys

path = sys.argv[1]
raw = open(path).read()
lines = raw.split('\n')
clean = []
for ln in lines:
    if ln.startswith('<!-- page'):
        continue
    if re.fullmatch(r'\s*\d{1,3}\s*', ln):
        continue
    if re.fullmatch(r'\s*Page \d+\s*', ln):
        continue
    clean.append(ln)
text = '\n'.join(clean)

blk_re = re.compile(r'(?m)^\s*((?:Cross-)?(?:Re-)?Examination|Questions?)\s+by\s+([A-Z][A-Za-z \.\'\-]{2,60})\s*$')
blocks = [(m.start(), m.group(1), m.group(2).strip()) for m in blk_re.finditer(text)]
wit_re = re.compile(r'(?m)^\s*([A-Z][A-Z .,\'\-]{3,60})\s*\((affirmed|sworn)\)')

out = []
for i, (pos, kind, examiner) in enumerate(blocks):
    end = blocks[i+1][0] if i+1 < len(blocks) else len(text)
    body = text[pos:end]
    decls = [m for m in wit_re.finditer(text[:pos])]
    witness = decls[-1].group(1).strip() if decls else '?'
    out.append(dict(i=i, kind=kind, examiner=examiner, witness=witness,
                    q=body.count('?'), chars=len(body), start=pos, end=end))

print(f"file: {path.split('/')[-1]}")
print(f"blocks: {len(out)}  total '?': {text.count('?')}")
print()
for b in out:
    print(f"[{b['i']:2d}] {b['kind']:<18} by {b['examiner'][:26]:<26} | witness {b['witness'][:28]:<28} | Q={b['q']:4d} chars={b['chars']:6d}")
json.dump(out, open('/tmp/pilot/blocks.json','w'), indent=1)
