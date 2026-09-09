import re
import sys

old = open(sys.argv[1], encoding="utf-8").read()  # docs/handoff/loi-v2-34-phien.md
news = [open(p, encoding="utf-8").read() for p in sys.argv[2:]]  # latest.md, rerun.md ...


def parse_old(t):
    out = {}
    for blk in re.split(r"\n### ", t)[1:]:
        sid = blk[:8]
        turns = []
        for m in re.finditer(r"\d+\. U: '(.*?)'\n.*?\n   B: '(.*?)'", blk, re.S):
            turns.append((m.group(1), m.group(2)))
        out[sid] = turns
    return out


def parse_new(t):
    out = {}
    for blk in re.split(r"\n## `", t)[1:]:
        sid = blk[:8]
        turns = []
        for m in re.finditer(r"- \*\*U:\*\* (.*?)\n  \*\*B:\*\* (.*?)\n  flags:", blk, re.S):
            turns.append((m.group(1).strip(), m.group(2).strip()))
        if turns:
            out[sid] = turns
    return out


o = parse_old(old)
n = {}
for t in news:
    n.update(parse_new(t))
for sid, turns in o.items():
    if sid not in n:
        continue
    print(f"\n### {sid}")
    for i, (u, b_old) in enumerate(turns):
        b_new = n[sid][i][1] if i < len(n[sid]) else "(thiếu)"
        print(f"U: {u[:70]}\n  CŨ : {b_old[:110]}\n  MỚI: {b_new[:110]}")
