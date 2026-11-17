import yaml, re, sys, json
src = open(sys.argv[1], encoding='utf-8').read().splitlines()
blocks, cur = [], []
def flush():
    global cur
    if cur: blocks.append('\n'.join(cur)); cur = []
for line in src:
    if line.startswith('- id:') or line.startswith('  ') or line.strip() == '---':
        if line.strip() == '---':
            flush(); continue
        cur.append(line)
    else:
        flush()
flush()
rub, prov = {}, {}
order = []
for b in blocks:
    items = yaml.safe_load(b)
    for it in items:
        if 'book' in it:
            assert it['id'] not in prov, it['id']; prov[it['id']] = it
        else:
            assert it['id'] not in rub, it['id']; rub[it['id']] = it; order.append(it['id'])
print(len(rub), len(prov), set(rub) ^ set(prov))
from collections import Counter
print(Counter(r['type'] for r in rub.values()))
json.dump({'order': order, 'rubric': rub, 'prov': prov}, open('parsed.json', 'w'), ensure_ascii=False, indent=1)
