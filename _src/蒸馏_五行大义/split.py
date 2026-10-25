# -*- coding: utf-8 -*-
"""按小节切分《五行大义》，剔除与八字无关篇目，贪心归并为若干块（每块 ≤8000 字，不切句）。"""
import os, re, json

SRC = r"C:/Users/PC/xwechat_files/wxid_sv0jv37mbo0j22_fd36/temp/RWTemp/2026-10/b135e1ddbfc84f7877251b3ff4e2759a/五行大义_殆知阁.txt"
BASE = r"C:/Users/PC/WorkBuddy/2026-10-25-14-45-26/蒸馏_五行大义"
OUT = os.path.join(BASE, "原文")
os.makedirs(OUT, exist_ok=True)

lines = open(SRC, encoding="utf-8").read().split("\n")

# (0-based 起始行, 小节名, 是否蒸馏)
SEC = [
    (69,  "释五行名", 1),
    (73,  "论支干名", 1),
    (77,  "辨体性", 1),
    (85,  "论五行及生成数", 1),
    (89,  "论支干数", 1),
    (93,  "论纳音数", 1),
    (97,  "论九宫数", 0),
    (113, "论相生·生死所·四时休王", 1),
    (127, "论配支干", 1),
    (131, "论相杂（五行体杂·支干杂·方位杂）", 1),
    (143, "论德", 1),
    (147, "论合", 1),
    (151, "论扶抑", 1),
    (155, "论相克", 1),
    (159, "论刑", 1),
    (163, "论害", 1),
    (167, "论冲破", 1),
    (175, "论配五色", 1),
    (179, "论配声音", 1),
    (183, "论配气味", 1),
    (187, "论配藏府", 1),
    (191, "论配五常", 1),
    (195, "论配五事", 1),
    (207, "论律吕", 0),
    (211, "论七政", 0),
    (215, "论八卦八风", 0),
    (219, "论情性", 1),
    (223, "论治政", 0),
    (235, "论诸神", 0),
    (239, "论五帝", 0),
    (243, "论诸官", 0),
    (247, "论人配五行", 1),
    (251, "论人游年年立", 1),
    (255, "论禽虫（五灵·三十六禽）", 0),
]

def clean(s):
    s = re.sub(r"^　　第[一二三四五六七八九十]+[^\n]{0,90}$\n?", "", s, count=1)
    return s.strip()

subs = []
for i, (start, name, keep) in enumerate(SEC):
    end = SEC[i + 1][0] if i + 1 < len(SEC) else len(lines)
    body = clean("\n".join(lines[start:end]))
    subs.append((name, keep, body))

kept = [(n, b) for n, k, b in subs if k and b]
excluded = [(n, len(b)) for n, k, b in subs if not k or not b]

# 贪心归并成块：按顺序累加，超过 8000 字就另起一块
blocks, cur, curname = [], [], []
for name, body in kept:
    if cur and sum(len(x[1]) for x in cur) + len(body) > 8000:
        blocks.append((curname, cur)); cur, curname = [], []
    cur.append((name, body)); curname.append(name)
if cur:
    blocks.append((curname, cur))

total = 0
index = []
for bi, (names, items) in enumerate(blocks, 1):
    text = "\n\n".join("【%s】\n%s" % (n, b) for n, b in items)
    tag = re.sub(r"[^\u4e00-\u9fa5]", "", names[0])[:8]
    fn = os.path.join(OUT, "%02d_%s.txt" % (bi, tag))
    open(fn, "w", encoding="utf-8").write(
        "《五行大义》（隋·萧吉）块 %d —— %s\n\n" % (bi, "／".join(names)) + text)
    total += len(text)
    index.append({"block": bi, "file": fn, "sections": names, "chars": len(text)})
    print("block %02d  %5d 字  %s" % (bi, len(text), "／".join(names)))

print("\n有效字数合计: %d   块数: %d   批数: %d" % (total, len(blocks), -(-len(blocks)//5)))
print("\n未蒸馏小节:")
for n, c in excluded:
    print("   -", n, c, "字")

json.dump({"total_chars": total, "blocks": index,
           "excluded": [{"name": n, "chars": c} for n, c in excluded]},
          open(os.path.join(BASE, "块索引.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
