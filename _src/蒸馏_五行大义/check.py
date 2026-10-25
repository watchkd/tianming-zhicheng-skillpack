# -*- coding: utf-8 -*-
import os, re, io

base = r"C:/Users/PC/WorkBuddy/2026-10-25-14-45-26/蒸馏_五行大义/技能包"
for d in sorted(os.listdir(base)):
    p = os.path.join(base, d, "SKILL.md")
    if not os.path.isfile(p):
        continue
    t = io.open(p, encoding="utf-8").read()
    first = t.split("\n")[0]
    name = re.search(r"^name:\s*(.+)$", t, re.M).group(1).strip()
    desc = re.search(r"^description:\s*(.+)$", t, re.M).group(1).strip()
    print("%-30s first=%-4r name_ok=%-6s desc=%3d chars" % (d, first, name == d, len(desc)))
