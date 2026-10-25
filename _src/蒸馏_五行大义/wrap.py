# -*- coding: utf-8 -*-
"""把续篇各节按句读折行，方便逐段阅读（不改原文一字，只加换行）。"""
import os, glob, textwrap, io

OUT = r"C:/Users/PC/WorkBuddy/2026-10-25-14-45-26/蒸馏_五行大义/阅读版"
os.makedirs(OUT, exist_ok=True)

for p in sorted(glob.glob(r"C:/Users/PC/WorkBuddy/2026-10-25-14-45-26/蒸馏_五行大义/原文_续/*.txt")):
    t = io.open(p, encoding="utf-8").read()
    # 先按句号/问号断句，再把长句硬折
    sents = t.replace("。", "。\n").replace("？", "？\n").replace("！", "！\n")
    lines = []
    for s in sents.split("\n"):
        s = s.strip()
        if not s:
            continue
        lines.extend(textwrap.wrap(s, 72) or [""])
    out = os.path.join(OUT, os.path.basename(p))
    io.open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("%-30s %d 行" % (os.path.basename(p), len(lines)))
